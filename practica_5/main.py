from hardware import *
from so import *
import log


##
##  MAIN
##
if __name__ == '__main__':
    log.setupLogger()
    log.logger.info('Starting emulator')

    ## setup our hardware and set memory size to 25 "cells"
    HARDWARE.setup(25)
    HARDWARE.cpu.enable_stats = True
    ## Switch on computer
    HARDWARE.switchOn()

    ## new create the Operative System Kernel
    # "booteamos" el sistema operativo

    # scheduler = SchedulerFCFS()
    # scheduler = SchedulerRoundRobin(3)
    # scheduler = SchedulerPriorityNonExpropiative()
    scheduler = SchedulerPriorityExpropiative()
    kernel = Kernel(scheduler, 4)

    gantt = GanttChart(kernel)
    HARDWARE.clock.addSubscriber(gantt)


    # Ahora vamos a intentar ejecutar 3 programas a la vez
    ##################
    prg0 = Program("PROGRAM-0.exe", [ASM.CPU(2), ASM.IO(), ASM.CPU(1)])
    prg1 = Program("PROGRAM-1.exe", [ASM.CPU(2)])
    prg2 = Program("PROGRAM-2.exe", [ASM.CPU(5)])

    kernel.file_system.write("D:/PROGRAM-0.exe", prg0)
    kernel.file_system.write("D:/PROGRAM-1.exe", prg1)
    kernel.file_system.write("D:/PROGRAM-2.exe", prg2)

    # execute all programs "concurrently"
    kernel.run("D:/PROGRAM-0.exe", 3)
    kernel.run("D:/PROGRAM-1.exe", 2)
    kernel.run("D:/PROGRAM-2.exe", 0)




