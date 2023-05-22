#!/usr/bin/env python

from hardware import *
import log


# emulates a compiled program
class Program:

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
                # is a list of instructions
                expanded.extend(i)
            else:
                # a single instr (a String)
                expanded.append(i)

        # now test if last instruction is EXIT
        # if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


# emulates an Input/Output device controller (driver)
class IoDeviceController:

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
            # pop(): extracts (deletes and return) the first element in queue
            pair = self._waiting_queue.pop(0)
            # print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)

    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(
            deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)


# emulates the  Interruptions Handlers
class AbstractInterruptionHandler:
    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))

    def pcb_out_handler(self, pcb_table, dispatcher):  # anteriormente: process_out_of_the_cpu
        scheduler = self.kernel.scheduler
        if not scheduler.ready_queue.is_empty():
            pcb_to_load = scheduler.get_next_process()
            pcb_to_load.state = State.RUNNING
            pcb_table.running_pcb = pcb_to_load
            dispatcher.load(pcb_to_load)
            log.logger.info(f"Now is running: {pcb_to_load})")
        else:
            pcb_table.running_pcb = None

    def pcb_in_handler(self, pcb_table, pcb_to_load, dispatcher):  # anteriormente: process_into_the_cpu
        pcb_running = pcb_table.running_pcb
        scheduler = self.kernel.scheduler
        if pcb_running is not None:
            if scheduler.must_expropriate(pcb_to_load, pcb_running):
                log.logger.info(f"CPU expropriation for: {pcb_to_load})")
                self.expropiative_context(pcb_table, pcb_to_load, pcb_running, scheduler, dispatcher)
                log.logger.info(f"Now is running: {pcb_to_load})")
            else:
                pcb_to_load.state = State.READY
                scheduler.enqueue_process(pcb_to_load)
        else:
            pcb_to_load.state = State.RUNNING
            pcb_table.running_pcb = pcb_to_load
            dispatcher.load(pcb_to_load)
            log.logger.info(f"Now is running: {pcb_to_load})")


    def expropiative_context(self, pcb_table, pcb_to_load, pcb_running, scheduler, dispatcher):
        pcb_expropriated = pcb_running
        pcb_table.running_pcb = None
        pcb_expropriated.state = State.READY
        dispatcher.save(pcb_expropriated)
        scheduler.enqueue_process(pcb_expropriated)
        dispatcher.load(pcb_to_load)
        pcb_to_load.state = State.RUNNING
        pcb_table.running_pcb = pcb_to_load


class NewInterruptionHandler(AbstractInterruptionHandler):
    def execute(self, irq):
        program = irq.parameters[0]
        priority = irq.parameters[1]
        loader = self.kernel.loader
        pcb_table = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher

        pid = pcb_table.generate_new_pid()
        program_base_dir = loader.load_program(program)
        pcb = PCB(pid, program_base_dir, 0, program.name, priority)
        pcb_table.add_pcb(pcb)
        log.logger.info(f"Adding program {program.name} as PCB with pid: {pid}")
        self.pcb_in_handler(pcb_table, pcb, dispatcher)


class KillInterruptionHandler(AbstractInterruptionHandler):
    def execute(self, irq):
        pcb_table = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher

        pcb = pcb_table.running_pcb
        pcb.state = State.TERMINATED
        dispatcher.save(pcb)
        pcb_table.running_pcb = None
        # pcb_table.remove_pcb(pcb.pid)
        self.pcb_out_handler(pcb_table, dispatcher)
        log.logger.info(f"Program finished: {pcb})")

        if pcb_table.theres_no_more_processes():
            HARDWARE.switchOff()


class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        operation = irq.parameters
        pcb_table = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher
        io_device_controller = self.kernel.ioDeviceController
        pcb = pcb_table.running_pcb
        pcb_table.running_pcb = None
        pcb.state = State.WAITING
        dispatcher.save(pcb)
        io_device_controller.runOperation(pcb, operation)
        log.logger.info(io_device_controller) 
        
        self.pcb_out_handler(pcb_table, dispatcher)


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcb = self.kernel.ioDeviceController.getFinishedPCB()
        pcb_table = self.kernel.pcb_table
        log.logger.info(self.kernel.ioDeviceController)
        dispatcher = self.kernel.dispatcher

        self.pcb_in_handler(pcb_table, pcb, dispatcher)


class TimeoutInterruptionHandler(AbstractInterruptionHandler):
    def execute(self, irq):
        scheduler = self.kernel.scheduler
        pcb_table = self.kernel.pcb_table
        dispatcher = self.kernel.dispatcher

        if not scheduler.ready_queue_is_empty():
            running_pcb = pcb_table.running_pcb
            pcb_table.running_pcb = None
            running_pcb.state = State.READY
            scheduler.enqueue_process(running_pcb)
            dispatcher.save(running_pcb)
            self.pcb_out_handler(pcb_table, dispatcher)
        else:
            HARDWARE.timer.reset()


class StatInterruptionHandler(AbstractInterruptionHandler):
    def execute(self, irq):
        if not self.kernel.pcb_table.theres_no_more_processes():
            self.agiging_ready_process(self.kernel.pcb_table.table)

    def agiging_ready_process(self, pcb_table):
        for pcb in pcb_table:
            pcb.aging()


class PCBTable():

    def __init__(self):
        self._table = []
        self._pid_actual = 0
        self._running_pcb = None

    @property
    def PCB(self, pid):
        return self._table[self._table.index(pid)]

    def add_pcb(self, new_pcb):
        self._table.append(new_pcb)

    def remove_pcb(self, pid):
        new_pcb_table = []
        for pcb in self._table:
            if pcb.pid != pid:
                new_pcb_table.append(pcb)
        self._table = new_pcb_table

    @property
    def running_pcb(self):
        return self._running_pcb

    @running_pcb.setter
    def running_pcb(self, pcb):
        self._running_pcb = pcb
        if pcb is not None:
            log.logger.info(f"Running PCB: {pcb.pid}")

    def generate_new_pid(self):
        pid = self._pid_actual
        self._pid_actual = self._pid_actual + 1
        return pid

    @property
    def table(self):
        return self._table

    def theres_no_more_processes(self):
        result = True
        for pcb in self.table:
            result = result and pcb.state == State.TERMINATED
        return result


# Process Control Block
class PCB:
    def __init__(self, pid, base_dir, pc, path, priority):
        self._pid = pid
        self._base_dir = base_dir
        self._pc = pc
        self._path = path
        self._state = State.READY
        self._priority = priority
        self._priority_aging = priority
        self._ready_time = 0

    @property
    def pid(self):
        return self._pid

    @property
    def base_dir(self):
        return self._base_dir

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

    @property
    def priority(self):
        return self._priority

    @property
    def ready_time(self):
        return self._ready_time

    @property
    def priority_aging(self):
        return self._priority_aging

    @ready_time.setter
    def ready_time(self, value):
        self._ready_time = value

    @priority_aging.setter
    def priority_aging(self, value):
        self._priority_aging = value

    def aging(self):
        if self.state == State.READY:
            if self.ready_time < 3:
                self.ready_time = self.ready_time + 1
            else:
                self.ready_time = 0
                if self.priority_aging > 1:
                    self.priority_aging = (self.priority_aging - 1)
                    log.logger.info(f"AGING PRIORITY: {self}")
        else:
            self.priority_aging = self.priority
            self.ready_time = 0

    def __repr__(self):
        return f"PCB(pid={self.pid}, base_dir={self.base_dir}, pc={self.pc}, state={self.state}, path={self.path},priority={self.priority_aging} "


class State:
    RUNNING = "RUNNING"
    READY = "READY"
    WAITING = "WAITING"
    TERMINATED = "TERMINATED"


class Dispatcher:

    def __init__(self, cpu, mmu, timer):
        self._cpu = cpu
        self._mmu = mmu
        self._timer = timer

    def load(self, pcb):
        self._cpu.pc = pcb.pc
        self._mmu.baseDir = pcb.base_dir  # no cambiar mmu.baseDir por mmu.base_dir
        self._timer.reset()
        log.logger.info(f"load pcb: {pcb.pid}")

    def save(self, pcb):
        pcb.pc = self._cpu.pc
        self._cpu.pc = -1
        log.logger.info(f"save pcb: {pcb.pid}")
    
    @property
    def timer(self):
        return self._timer


class Queue:
    def __init__(self):
        self._queue = []

    def add_process(self, process):
        self._queue.append(process)

    def get_first_process(self):
        if not self.is_empty():
            return self._queue.pop(0)
        else:
            return None

    def is_empty(self):
        return not self._queue


class PriorityQueue:

    def __init__(self):
        self._queue = []

    def add_process(self, process):
        self._queue.append(process)

    def get_first_process(self):
        max_priority_pcb = self._queue[0]
        current_max_priority = max_priority_pcb.priority_aging
        for pcb in self._queue:
            # menor igual resuelve desempate por FIFO
            if pcb.priority <= current_max_priority:
                max_priority_pcb = pcb
                current_max_priority = max_priority_pcb.priority_aging
        self._queue.remove(max_priority_pcb)
        return max_priority_pcb

    def is_empty(self):
        return not self._queue


class Loader:
    def __init__(self):
        self._memory_pos = 0

    def load_program(self, program):
        base_dir_prg = self._memory_pos
        first_available_dir = self._memory_pos
        for index in range(0, len(program.instructions)):
            inst = program.instructions[index]
            HARDWARE.memory.write(first_available_dir, inst)
            first_available_dir += 1
        self._memory_pos = first_available_dir
        return base_dir_prg

    @property
    def memory_pos(self):
        return self._memory_pos

    @memory_pos.setter
    def memory_pos(self, value):
        self._memory_pos = value


class SchedulerFCFS:
    def __init__(self):
        self._ready_queue = Queue()

    @staticmethod
    def must_expropriate(pcb_ready, pcb_running):
        return False

    @property
    def ready_queue(self):
        return self._ready_queue

    def ready_queue_is_empty(self):
        return self.ready_queue.is_empty()

    # Estos 2 metodos lo comparten SchedulerFCFS y SchedulerRoundRobin, no sé si debería estar en la clase hija también, aunque dudo bastante
    def enqueue_process(self, process):
        self.ready_queue.add_process(process)

    def get_next_process(self):
        return self.ready_queue.get_first_process()


class SchedulerRoundRobin(SchedulerFCFS):
    def __init__(self, quantum):
        super(SchedulerRoundRobin, self).__init__()
        HARDWARE.timer.quantum = quantum
        self._quantum = quantum
        self._quantumActual = 0


class SchedulerPriorityNonExpropiative:
    def __init__(self):
        self._ready_queue = PriorityQueue()

    def must_expropriate(self, _, __):
        return False

    @property
    def ready_queue(self):
        return self._ready_queue

    def ready_queue_is_empty(self):
        return self._ready_queue.is_empty()

    def enqueue_process(self, process):
        self._ready_queue.add_process(process)

    def get_next_process(self):
        return self.ready_queue.get_first_process()


class SchedulerPriorityExpropiative(SchedulerPriorityNonExpropiative):
    def __init__(self):
        super(SchedulerPriorityExpropiative, self).__init__()

    @staticmethod
    def must_expropriate(pcb_ready, pcb_running):
        return pcb_ready.priority_aging < pcb_running.priority_aging


# emulates the core of an Operative System
class Kernel:

    def __init__(self, scheduler):
        # setup interruption handlers
        kill_handler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, kill_handler)

        io_in_handler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, io_in_handler)

        io_out_handler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, io_out_handler)

        new_handler = NewInterruptionHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, new_handler)

        time_out_handler = TimeoutInterruptionHandler(self)
        HARDWARE.interruptVector.register(TIMEOUT_INTERRUPTION_TYPE, time_out_handler)

        stat_handler = StatInterruptionHandler(self)
        HARDWARE.interruptVector.register(STAT_INTERRUPTION_TYPE, stat_handler)

        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)

        self._loader = Loader()

        self._pcb_table = PCBTable()

        self._dispatcher = Dispatcher(HARDWARE.cpu, HARDWARE.mmu, HARDWARE.timer)

        self._scheduler = scheduler

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def loader(self):
        return self._loader

    @property
    def pcb_table(self):
        return self._pcb_table

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def scheduler(self):
        return self._scheduler

    def get_ready_queue(self):
        return self._scheduler.ready_queue

    def load_program(self, program):
        return self._loader.load_program(program)

    def run(self, program, priority):
        new_irq = IRQ(NEW_INTERRUPTION_TYPE, (program, priority))
        HARDWARE._interruptVector.handle(new_irq)
        log.logger.info("\n Loading program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)

    def __repr__(self):
        return "Kernel "


class GanttChart:

    def __init__(self, kernel):
        self._kernel = kernel
        self._repr = []
        self._headers = ["process"]

    def tick(self, tick_num):
        if tick_num == 1:  # armo template en el momento 1
            self._repr = self.do_template(self._kernel.pcb_table.table)
            self.update(tick_num, self._kernel.pcb_table.table)
        if tick_num > 1:  # siempre que haya ticks sigo actualizando
            self.update(tick_num, self._kernel.pcb_table.table)
        if self.all_finished():
            log.logger.info(self.__repr__())

    def update(self, nro_tick, pcb_table):
        self._headers.append(nro_tick)
        pnum = 0
        for pcb in pcb_table:
            if pcb.state == State.RUNNING:
                character = "R"
            if pcb.state == State.WAITING:
                character = "w"
            if pcb.state == State.READY:
                character = "."
            if pcb.state == State.TERMINATED:
                character = " "
            self._repr[pnum].append(character)
            pnum = pnum + 1

    def do_template(self, pcb_table):
        lista = []
        for pcb in pcb_table:
            lista.append([pcb.path])
        return lista

    def all_finished(self):
        return self._kernel.pcb_table.theres_no_more_processes()

    def __repr__(self):
        return tabulate(self._repr, headers=self._headers, tablefmt='grid', stralign='center')

