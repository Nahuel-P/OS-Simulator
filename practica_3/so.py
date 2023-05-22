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


## emulates an Input/Output device controller (driver)
class IoDeviceController():

    def __init__(self, device):
        self._device = device
        self._waiting_queue = []
        self._currentPCB = None

    def runOperation(self, pcb, instruction):
        pair = {'pcb': pcb, 'instruction': instruction}
        # append: adds the element at the end of the queue
        self._waiting_queue.append(pair)
        # try to send the instruction to hardware's device (if is idle)
        self.__load_from_waiting_queue_if_apply()

    def getFinishedPCB(self):
        finishedPCB = self._currentPCB
        self._currentPCB = None
        self.__load_from_waiting_queue_if_apply()
        return finishedPCB

    def __load_from_waiting_queue_if_apply(self):
        if (len(self._waiting_queue) > 0) and self._device.is_idle:
            ## pop(): extracts (deletes and return) the first element in queue
            pair = self._waiting_queue.pop(0)
            # print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)

    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(
            deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)


## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():
    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))


class NewInterruptionHandler(AbstractInterruptionHandler):
    def execute(self, irq):
        program = irq.parameters
        loader = self.kernel.loader
        pcb_table = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher
        ready_queue = self.kernel.ready_queue

        pid = pcb_table.generate_new_pid()
        program_base_dir = loader.load(program)
        pcb = PCB(pid, program_base_dir, 0, program.name)
        pcb_table.add_pcb(pcb)

        process_into_the_cpu(ready_queue, pcb_table, pcb, dispatcher)


class KillInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcbTable = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher
        readyQueue = self.kernel.ready_queue

        pcb = pcbTable.get_running_pcb()
        dispatcher.save(pcb)
        pcb.state = State.TERMINATED
        pcbTable.remove_pcb(pcb.pid)

        log.logger.info(" Program Finished ")

        process_out_of_the_cpu(readyQueue, pcbTable, dispatcher)


class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        operation = irq.parameters
        pcbTable = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher
        ioDeviceController = self.kernel.ioDeviceController
        readyQueue = self.kernel.ready_queue
        pcb = pcbTable.get_running_pcb()

        dispatcher.save(pcb)
        pcb.state = State.WAITING
        ioDeviceController.runOperation(pcb, operation)
        log.logger.info(ioDeviceController)

        process_out_of_the_cpu(readyQueue, pcbTable, dispatcher)


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcb = self.kernel.ioDeviceController.getFinishedPCB()
        pcbTable = self.kernel.pcb_table
        readyQueue = self.kernel.ready_queue
        log.logger.info(self.kernel.ioDeviceController)
        dispatcher = self.kernel.dispatcher

        process_into_the_cpu(readyQueue, pcbTable, pcb, dispatcher)


class PCBTable():
    def __init__(self):
        self._table = []
        self._pidActual = 0
        self._runningPCB = None

    @property
    def PCB(self, pid):
        return self._table[self._table.index(pid)]

    def add_pcb(self, newPCB):
        self._table.append(newPCB)

    def remove_pcb(self, pid):
        new_pcb_table = []
        for pcb in self._table:
            if pcb.pid != pid:
                new_pcb_table.append(pcb)
        self._table = new_pcb_table

    def running_pcb(self, pcb):
        self._runningPCB = pcb

    def get_running_pcb(self):
        return self._runningPCB

    def generate_new_pid(self):
        pid = self._pidActual
        self._pidActual = self._pidActual + 1
        return pid


# Process Control Block
class PCB:
    def __init__(self, pid, base_dir, pc, path):
        self._pid = pid
        self._baseDir = base_dir
        self._pc = pc
        self._path = path
        self._state = State.READY

    @property
    def pid(self):
        return self._pid

    @property
    def base_dir(self):
        return self._baseDir

    @property
    def pc(self):
        return self._pc

    @property
    def path(self):
        return self._path

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        self._state = state

    @pc.setter
    def pc(self, pc):
        self._pc = pc


class State:
    RUNNING = "RUNNING"
    READY = "READY"
    WAITING = "WAITING"
    TERMINATED = "TERMINATED"


class Dispatcher:

    def __init__(self, cpu, mmu):
        self._cpu = cpu
        self._mmu = mmu

    def load(self, pcb):
        self._cpu.pc = pcb.pc
        self._mmu.baseDir = pcb.base_dir
        log.logger.info(f"load pcb:{pcb}")

    def save(self, pcb):
        pcb.pc = self._cpu.pc
        self._cpu.pc = -1
        log.logger.info(f"save pcb:{pcb}")


class ReadyQueue:
    def __init__(self):
        self._queue = []

    def add(self, pcb):
        self._queue.append(pcb)

    def next(self):
        if not self.is_empty():
            return self._queue.pop(0)
        else:
            return None

    def is_empty(self):
        return not self._queue


class Loader:
    def __init__(self):
        self._memoryPos = 0

    def load(self, program):
        base_dir_prg = self._memoryPos
        first_available_dir = self._memoryPos
        for index in range(0, len(program.instructions)):
            inst = program.instructions[index]
            HARDWARE.memory.write(first_available_dir, inst)
            first_available_dir += 1
        self._memoryPos = first_available_dir
        return base_dir_prg

    @property
    def memory_pos(self):
        return self._memoryPos

    @memory_pos.setter
    def memory_pos(self, value):
        self._memoryPos = value


# emulates the core of an Operative System
class Kernel:

    def __init__(self):
        # setup interruption handlers
        kill_handler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, kill_handler)

        io_in_handler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, io_in_handler)

        io_out_handler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, io_out_handler)

        new_handler = NewInterruptionHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, new_handler)

        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)

        self._loader = Loader()

        self._ready_queue = ReadyQueue()

        self._pcb_table = PCBTable()

        self._dispatcher = Dispatcher(HARDWARE.cpu, HARDWARE.mmu)

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def loader(self):
        return self._loader

    @property
    def ready_queue(self):
        return self._ready_queue

    @property
    def pcb_table(self):
        return self._pcb_table

    @property
    def dispatcher(self):
        return self._dispatcher

    def load_program(self, program):
        return self._loader.load(program)

    def run(self, program):
        new_irq = IRQ(NEW_INTERRUPTION_TYPE, program)
        HARDWARE._interruptVector.handle(new_irq)
        log.logger.info("\n Loading program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)

    def __repr__(self):
        return "Kernel "


def process_out_of_the_cpu(ready_queue, pcb_table, dispatcher):
    if not ready_queue.is_empty():
        pcb_to_load = ready_queue.next()
        pcb_to_load.state = State.RUNNING
        dispatcher.load(pcb_to_load)
        pcb_table.running_pcb(pcb_to_load)
    else:
        pcb_table.running_pcb(None)


def process_into_the_cpu(ready_queue, pcb_table, pcb_to_load, dispatcher):
    if pcb_table.get_running_pcb():
        pcb_to_load.state = State.READY
        ready_queue.add(pcb_to_load)
    else:
        pcb_to_load.state = State.RUNNING
        pcb_table.running_pcb(pcb_to_load)
        dispatcher.load(pcb_to_load)
