#!/usr/bin/env python

from hardware import *
import log



## emulates a compiled program
class Program():

    def __init__(self, name, instructions):
        self._name = name
        self._instructions = self.expand(instructions)

    @property
    def name(self):
        return self._name

    @property
    def instructions(self):
        return self._instructions

    def addInstr(self, instruction):
        self._instructions.append(instruction)

    def expand(self, instructions):
        expanded = []
        for i in instructions:
            if isinstance(i, list):
                ## is a list of instructions
                expanded.extend(i)
            else:
                ## a single instr (a String)
                expanded.append(i)
            
        ## now test if last instruction is EXIT
        ## if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():
    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))



class KillInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        log.logger.info(" Program Finished ")
        # por ahora apagamos el hardware porque estamos ejecutando un solo programa
        if self.kernel.has_program_ready_to_run():
            self.kernel.runNextProgram()
        else:
            HARDWARE.switchOff()

# emulates the core of an Operative System
class Kernel():

    @property
    def programs(self):
        return self._programs

    def __init__(self):
        ## setup interruption handlers
        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)
        self._programs = []

    def has_program_ready_to_run(self):
        return self._programs

    def nextProgram(self):
        return self._programs.pop(0)



    def load_program(self, program):
        # loads the program in main memory  
        progSize = len(program.instructions)
        for index in range(0, progSize):
            inst = program.instructions[index]
            HARDWARE.memory.write(index, inst)

    ## emulates a "system call" for programs execution  
    def run(self, program):
        self.load_program(program)
        log.logger.info("\n Executing program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)

        # set CPU program counter at program's first intruction
        HARDWARE.cpu.pc = 0

    def execute_batch(self, batch):
        """
        Executes a list of programs sequentially, also known as batch
        args:
          batch: a list of programs to be executed
        returns: None
        """
        if batch:
            for program in batch:
                self._programs.append(program)

            self.runNextProgram()

    def runNextProgram(self):
        self.run(self.nextProgram())

    def __repr__(self):
        return "Kernel "
