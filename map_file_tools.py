"""
Experimental tool to handle iOS crash log prodused by marmalade

THIS TOOL CAN HELP FOUND VERY RARE BUGS IN YOU CODE

WARNING NOT FOR PRODUCTION, ONLY FOR TESTING IN QA

You need modify the you programm and add function to make crush.

For example i use this method:

void Crush_VIA_SIGSEGV()
{
	*((int*)(NULL)) = 42;
}

And modify the programm to make crashlog after first start
Something like this:
if(!file_is_exist("crashlog_created"))
{
	create_file("crashlog_created");
	Crush_VIA_SIGSEGV();
}

After each build you need to save *.map file in output folder

After this, when each new version of application starts is firstly create crushlog.
The first craslog need us to calculate offset of functions in the executable relative to map file adresses.
This is because we dont know real offset after s3eRelocate

When you application crushed with REAL bug, grab crashlogs from device.

and call the this script:

python map_file_tools.py --map="you_saved_map_file.map" --test_crashlog="theFirstCrashlogByCrush_VIA_SIGSEGV.crash" --symbol="Crush_VIA_SIGSEGV()" --crash="craslog_by_rare_bug.crash"

Author: Alex A Ermoshenko (.erax)

"""
import sys, getopt
import re

map_file = False
example_crashlog = False
work_crashlog = False
example_crashlog_symbol_name = False

symbolicatedCrashlog = False



def usage_and_exit():
	print 'map_file_tools.py --map=map_file.map --test_crashlog=Crush_VIA_SIGSEGV.crash --symbol=Crush_VIA_SIGSEGV() --crash=crashlog.crash [--out=out.crush]'
	sys.exit(2)


try:
	opts, args = getopt.getopt(sys.argv[1:],"::mtcso",["map=", "test_crashlog=", "crash=", "symbol=", "out="])
except getopt.GetoptError:
	usage_and_exit()
for opt, arg in opts:
	if opt in ('-m', '--map'):
		map_file = arg
	elif opt in ('-t', '--test_crashlog'):
		example_crashlog = arg
	elif opt in ('-c', '--crash'):
		work_crashlog = arg
	elif opt in ('-s', '--symbol'):
		example_crashlog_symbol_name = arg
	elif opt in ('-o', '--out'):
		symbolicatedCrashlog = arg

if not map_file:
	print 'Mapfile not specified\n'
	usage_and_exit();

if not example_crashlog:
	print 'Test crashlog not specified\n'
	usage_and_exit();

if not example_crashlog_symbol_name:
	print 'Symbol name not specified\n'
	usage_and_exit();
	
	
if not work_crashlog:
	print 'Work crashlog not specified\n'
	usage_and_exit();
	
	
	
if not (map_file and example_crashlog and work_crashlog and example_crashlog_symbol_name):
	usage_and_exit()



def load_pc_and_lr_register_from_crashlog(file):
	pattern = "lr:\W+(0x[0-9a-f]+)\W+pc:\W+(0x[0-9a-f]+)"
	#Pattern to read LR and PC registers from crashlog
	#
	#Simple
	#lr:\W+0x[0-9a-f]+\W+pc:\W+0x[0-9a-f]+
	#
	#With groups
	#lr:\W+(0x[0-9a-f]+)\W+pc:\W+(0x[0-9a-f]+)
	#
	#interest part of crushlog example:
	#Thread 4 crashed with ARM Thread State (32-bit):
	#r0: 0x079bd430    r1: 0x00000000      r2: 0x0000002a      r3: 0x000000ff
	#r4: 0x00000001    r5: 0x027b9f00      r6: 0x027b9e00      r7: 0x027b9f80
	#r8: 0x027b9f94    r9: 0x00000000     r10: 0x00000000     r11: 0x00000000
	#ip: 0x00000000    sp: 0x027b9c88      lr: 0x000ca91c      pc: 0x000ca748
	#cpsr: 0x60000010
	#
	#
	#Match part of input is: "lr: 0x000ca91c      pc: 0x000ca748"
	#The first group is value of LR register, and second is value of PC register
	
	#identifier
	#^Identifier:\W(.*)		
	identifierPattern = '[\n\r]Identifier:\W+(.*)'

	
	with open(file) as f:
		result = []
		content = f.read()
		regs = re.findall(pattern, content)
		if len(regs) != 1:
			print 'Bad crashlog ', file
			sys.exit(0)
		
		identifiers = re.findall(identifierPattern, content)
		if len(identifiers) != 1:
			print 'Bad crashlog (multiple identifiers)', file
			sys.exit(0)
		
		match = regs[0];
		return {'lr':eval(match[0]), 'pc':eval(match[1]), 'id':identifiers[0]}

def load_noncomplite_symbols(file):
	#\.[\w.]+[\W]*0x[0-9a-f]+[\W]*0x[0-9a-f]+[\W]+[\w|\.|/|(|)| |-]+
	with open(file) as f:
		result = []
		content = f.read()
		pattern = "(\.[\w.]+[\W]*(0x[0-9a-f]+)[\W]*(0x[0-9a-f]+)[\W]+([\w|\.|/|(|)| |-]+))"

		all = re.findall(pattern, content)
		
		#print all
		
		for entry in all:
			addr = eval(entry[1])
			size = eval(entry[2])
			if addr > 0 and size > 0 and size != addr:
				obj = { 'text':	entry[0],
						'obj': entry[3],
						'addr':		addr,
						'map.addr':	addr,
						'size':		size}
				result.append(obj)
		return result

	
		
def load_symbols(file):
	with open(file) as f:
		result = []
		content = f.read()
		#Pattern for read map file info
		#
		#Simple
		#\.[\w]+\.[\w]+[\W]*0x[0-9a-f]+[\W]*0x[0-9a-f]+[\W]+[\w|\.|/]+[\W]+0x[0-9a-f]+[\W]+.+
		#
		#With groups
		#\.(?P<segment>[\w]+)\.(?P<obf>[\w]+)[\W]*(?P<address>0x[0-9a-f]+)[\W]*(?P<size>0x[0-9a-f]+)[\W]+(?P<obj>[\w|\.|/]+)[\W]+0x[0-9a-f]+[\W]+(?P<func>.+)
		#Example input
		# .text.main     0x4a0003b4       0x54 ./Debug_s3eFacebook_vc9x_gcc_arm/main.obj
		#                0x4a0003b4                main
		# .text._Z9NewButtonPKcPFvP6ButtonE
		#                0x4a000408      0x1c0 ./Debug_s3eFacebook_vc9x_gcc_arm/Buttons.obj
		#                0x4a000408                NewButton(char const*, void (*)(Button*))
		# .text._Z13DeleteButtonsv
		#                0x4a0005c8       0xac ./Debug_s3eFacebook_vc9x_gcc_arm/Buttons.obj
		#                0x4a0005c8                DeleteButtons()
		#
		#First entire match:
		# .text.main     0x4a0003b4       0x54 ./Debug_s3eFacebook_vc9x_gcc_arm/main.obj
		#                0x4a0003b4                main
		#Second entire match
		# .text._Z13DeleteButtonsv
		#                0x4a0005c8       0xac ./Debug_s3eFacebook_vc9x_gcc_arm/Buttons.obj
		#                0x4a0005c8                DeleteButtons()
		
		
		pattern = "\.(?P<segment>[\w]+)\.(?P<obf>[\w]+)[\W]*(?P<address>0x[0-9a-f]+)[\W]*(?P<size>0x[0-9a-f]+)[\W]+(?P<obj>[\(\)\.\w/ -]+)[\W]+0x[0-9a-f]+[\W]+(?P<func>.+)"

		all = re.findall(pattern, content)
		
		#print all
		
		for entry in all:
			addr = eval(entry[2])
			if addr > 0:
				obj = { 'segment':	entry[0],
						'sysName':	entry[1],
						'addr':		addr,
						'map.addr':	addr,
						'size':		eval(entry[3]),
						'obj':		entry[4],
						'name':		entry[5]}
				result.append(obj)
				#print obj
		return result

		
		
def get_addr_of(symbols, func):
	for symbol in symbols:
		if symbol['name'] == func or symbol['sysName'] == func:
			return symbol['addr']
	return 0
	
def relocate(symbols, oldBase, newBase):
	result = []
	for symbol in symbols:
		symbol['addr'] = symbol['addr'] + (newBase - oldBase)
		if symbol['addr'] < 0:
			print "Bad relocate ", symbol
		result.append(symbol)
	return result
	
def get_symbol_at(symbols, address):
	for symbol in symbols:
		addr = symbol['addr']
		size = symbol['size']
		if  address >= addr and address < (addr+size):
			return symbol
	return False

def get_func_at_list(symbols, address):
	for symbol in symbols:
		addr = symbol['addr']
		size = symbol['size']
		if  address >= addr and address < (addr+size):
			yield symbol['name']

def get_symbol_at_list(symbols, address):
	for symbol in symbols:
		addr = symbol['addr']
		size = symbol['size']
		if  address >= addr and address < (addr+size):
			yield symbol

def get_symbol_at_with_smallest_size(symbols, address):
	result = False
	size = 2**32
	for symbol in get_symbol_at_list(symbols, address):
		if size > symbol['size']:
			result = symbol
			size = symbol['size']
	return result

unknownFunction = "????"

def get_func_at(symbols, nonCompliteSymbols, address, offset_to_relocate):
	l = list(get_func_at_list(symbols, address))
	if len(l) == 0:
		symbol = get_symbol_at_with_smallest_size(nonCompliteSymbols, address - offset_to_relocate)
		if not symbol:
			return unknownFunction
		return symbol['obj']
	if len(l) > 1:
		return "Ambigous function, this is error situation. Variants:", l
	return l[0]
			
def addr_to_str(addr):
	return "0x%0.8X" % addr
	
	
def symbolicate(symbols,nonCompliteSymbols, inputCrashlog, outputCrashlog, projectName, offset_to_relocate):
	stackLine =  '(\d+\W+{project_name}\W+(0x[0-9a-f]+)\W+0x[0-9a-f]+\W+\+\W+[0-9]+)'
	
	projectName = projectName.replace('"', '\"')
	projectName = projectName.replace('[', '\[')
	projectName = projectName.replace(']', '\]')
	projectName = projectName.replace('(', '\(')
	projectName = projectName.replace(')', '\)')
	
	stackLinePattern = stackLine.format(project_name = projectName);
	#print stackLinePattern;
	
	with open(inputCrashlog) as f:
		content = f.read()
		all = re.findall(stackLinePattern, content)
		
		for line, address in all:
			func = get_func_at(symbols, nonCompliteSymbols, eval(address), offset_to_relocate)
			lineWithFunc = line + "\t" + func
			content = content.replace(line, lineWithFunc);

	with open(outputCrashlog, 'w+') as file:
		file.write(content)

	pass
		
symbols = load_symbols(map_file)
nonCompliteSymbols = load_noncomplite_symbols(map_file)

symbols.sort(lambda a,b: a['addr'] - b['addr'])
nonCompliteSymbols.sort(lambda a,b: a['addr'] - b['addr'])

#print 'Base addr ', addr_to_str(symbols[0]['addr']), symbols[0]['name'], symbols[0]['sysName'] 

#print 'Address of main function BEFORE, ', addr_to_str(get_addr_of(symbols, 'main'))


addrOfCrushSite = get_addr_of(symbols, example_crashlog_symbol_name)

if addrOfCrushSite == 0:
	print "Symbol", example_crashlog_symbol_name, "not found in map file."
	sys.exit(0)

registersExample = load_pc_and_lr_register_from_crashlog(example_crashlog)
pc_registerValueOfCrushSite = registersExample['pc']

registers = load_pc_and_lr_register_from_crashlog(work_crashlog)


if registersExample['id'] != registers['id']:
	print "Identifiers of crushlogs not the same", registersExample['id'], " != ", registers['id']
	sys.exit(0)

projectName = registersExample['id']

offset_to_relocate = pc_registerValueOfCrushSite - addrOfCrushSite


print ""

print 'Project name      :   ', projectName
print 'Main function addr:   ', addr_to_str(get_addr_of(symbols, 'main'))
print 'Relocate with offset  ', addr_to_str((addrOfCrushSite - pc_registerValueOfCrushSite))
print 'Relocate 0x4a000000 + ', addr_to_str(0x4a000000 - (addrOfCrushSite - pc_registerValueOfCrushSite))


#symbols = relocate(symbols, get_addr_of(symbols, 'Crush1()'), 0xca738)
#symbols = relocate(symbols, 0x4A003830, 0xca738)
symbols = relocate(symbols, addrOfCrushSite, pc_registerValueOfCrushSite)
#nonCompliteSymbols = relocate(nonCompliteSymbols, addrOfCrushSite, pc_registerValueOfCrushSite)

#print 'Address of main function AFTER, ', addr_to_str(get_addr_of(symbols, 'main'))

#newBase = 0x1000

#functions = ['main', 'Crush1()', 'Crush2()']

#for fn in functions:
#	a = get_addr_of(symbols, fn)
	#print "  ", fn, addr_to_str(a), "  ", addr_to_str(newBase), " + ", (a - newBase)
	

#print addr_to_str(get_addr_of(symbols, 'Crush1()'))


lr = registers['lr']
pc = registers['pc']


if not get_symbol_at(symbols, pc):
	print "Symbols not found at addresses PC:", addr_to_str(pc)
	print "Symbols address in map file space:",addr_to_str(pc - offset_to_relocate)
	symbol = get_symbol_at_with_smallest_size(nonCompliteSymbols, pc - offset_to_relocate)
	if not symbol:
		print "MAP File not contains any records at this address"
	else:
		print symbol['text']

if not get_symbol_at(symbols, lr):
	print "Symbols not found at addresses LR:", addr_to_str(lr)
	print "Symbols address in map file space:",addr_to_str(lr - offset_to_relocate)
	symbol = get_symbol_at_with_smallest_size(nonCompliteSymbols, pc - offset_to_relocate)
	if not symbol:
		print "MAP File not contains any records at this address"
	else:
		print symbol['text']

if not get_symbol_at(symbols, pc) and not get_symbol_at(symbols, lr):
	sys.exit(0)

p = get_func_at(symbols,nonCompliteSymbols, pc, offset_to_relocate)
l = get_func_at(symbols,nonCompliteSymbols, lr, offset_to_relocate)

print "\n"

print "PC in:", p
print "LR in:", l

print "\n"
print "Explained:\n"

print "Crush in the function:\n\t", p
print "This function called from function:\n\t", l

if l == p:
	print ""
	print "LR and PC points to the same function, and i dont know why."
	print "May be method of determining offsets have mistake around 8 or 16 bytes"
	print ""
	print "Symbol info dump:"
	sym = get_symbol_at(symbols, pc)
	po = pc - sym['addr']
	lo = lr - sym['addr']
	print "    Name:         ", sym['sysName']
	print "    Readable name:", sym['name']
	print "    Address:      ", addr_to_str(sym['addr']), "PC -",addr_to_str(po),"(",po,") " "LR -",addr_to_str(lo), "(", lo,")"
	print "    Size:         ", sym['size']
	print "    MAP File addr:", addr_to_str(sym['map.addr'])
	print "    PC Value is:  ",addr_to_str(pc)
	print "    LR Value is:  ",addr_to_str(lr)
	print ""
	print "PC-8  in:", get_func_at(symbols, pc-8)
	print "LR-8  in:", get_func_at(symbols, lr-8)
	print ""
	print "PC-16 in:", get_func_at(symbols, pc-16)
	print "LR-16 in:", get_func_at(symbols, lr-16)
	print ""
	print "PC+8  in:", get_func_at(symbols, pc+8)
	print "LR+8  in:", get_func_at(symbols, lr+8)
	print ""
	print "PC+16 in:", get_func_at(symbols, pc+16)
	print "LR+16 in:", get_func_at(symbols, lr+16)
	
if symbolicatedCrashlog:
	symbolicate(symbols,nonCompliteSymbols, work_crashlog, symbolicatedCrashlog, projectName, offset_to_relocate)
	



	
			
				
			
			
		