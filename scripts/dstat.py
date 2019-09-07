#!/usr/bin/env python

import sys
import argparse
import os
import time
import datetime
import psutil
import shutil
import signal

# === mac ===
# >>> psutil.cpu_stats()
# scpustats(ctx_switches=16581, interrupts=656044, soft_interrupts=779785455, syscalls=578372)
# >>> psutil.cpu_times_percent()
# scputimes(user=8.6, nice=0.0, system=3.3, idle=88.0)
#
# === linux ===
# >>> psutil.cpu_times_percent()
# scputimes(user=1.5, nice=0.0, system=0.1, idle=97.8, iowait=0.0, irq=0.0, softirq=0.5, steal=0.1, guest=0.0, guest_nice=0.0)
# >>> psutil.cpu_stats()
# scpustats(ctx_switches=10839719127, interrupts=8227216711, soft_interrupts=14619700996, syscalls=0)

class Time:
    def header0(self):
        return '--------system---------'
    def header1(self):
        return '         time          '
    def value(self):
        return datetime.datetime.now().isoformat(timespec='milliseconds')

class LoadAvg:
    def header0(self):
        return '---load-avg---'
    def header1(self):
        return ' 1m   5m  15m '
    def value(self):
        loads = (('%.3f' % load)[:4] for load in psutil.getloadavg())
        return ' '.join(loads)

class CpuUsage:
    # === mac ===
    # >>> psutil.cpu_times_percent()
    # scputimes(user=8.6, nice=0.0, system=3.3, idle=88.0)
    #
    # === linux ===
    # >>> psutil.cpu_times_percent()
    # scputimes(user=1.5, nice=0.0, system=0.1, idle=97.8, iowait=0.0, irq=0.0, softirq=0.5, steal=0.1, guest=0.0, guest_nice=0.0)

    ABBRS = {
        'user': 'usr',
        'nice': 'nic',
        'system': 'sys',
        'idle': 'idl',
        'irq': 'hiq',
        'softirq': 'siq',
        'steal': 'stl',
        'guest': 'gst',
        'guest_nice': 'gni',
    }

    def __init__(self):
        cputimes = psutil.cpu_times_percent()
        abbrs = [self.ABBRS[f] for f in cputimes._fields]
        self._header1 = ' '.join(abbrs)
        space_to_fill = len(self._header1) - len('total-cpu-usage')
        self._header0 = '-' * (space_to_fill // 2) + 'total-cpu-usage' + '-' * (space_to_fill // 2)

    def header0(self):
        return self._header0

    def header1(self):
        return self._header1

    def value(self):
        cputimes = psutil.cpu_times_percent()
        result = ' '.join(('%.3f' % t)[:3] for t in cputimes)
        return result

def pretty_bytes(num, b=' '):
    for x in [b, 'k', 'm', 'g', 't', 'p']:
        if num < 1024.0:
            return "%4.0f%s" % (num, x)
        num /= 1024.0

class DiskStats:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.disk_io_counters()

    def header0(self):
        return '-dsk/total-'

    def header1(self):
        return ' read  writ'

    def value(self):
        t = time.time()
        values = psutil.disk_io_counters()

        elapsed = t - self.last_time
        read_bytes = values.read_bytes - self.last_values.read_bytes
        write_bytes = values.write_bytes - self.last_values.write_bytes

        read_rate = pretty_bytes(read_bytes / elapsed)
        write_rate = pretty_bytes(write_bytes / elapsed)

        result = '%s %s' % (read_rate, write_rate)

        self.last_time = t
        self.last_values = values

        return result

class NetStats:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.net_io_counters()

    def header0(self):
        return '-net/total-'

    def header1(self):
        return ' recv  send'

    def value(self):
        t = time.time()
        values = psutil.net_io_counters()

        elapsed = t - self.last_time
        bytes_recv = values.bytes_recv - self.last_values.bytes_recv
        bytes_sent = values.bytes_sent - self.last_values.bytes_sent

        recv_rate = pretty_bytes(bytes_recv / elapsed, 'B')
        send_rate = pretty_bytes(bytes_sent / elapsed, 'B')

        result = '%s %s' % (recv_rate, send_rate)

        self.last_time = t
        self.last_values = values

        return result

class MemUsage:
    # TODO add support for buff/cached (not available on mac)

    def header0(self):
        return '-mem-usage-'

    def header1(self):
        return ' used  free'

    def value(self):
        vm = psutil.virtual_memory()
        return '%s %s' % (pretty_bytes(vm.used), pretty_bytes(vm.available))

# def print_header():
#     print('--------system--------- ---load-avg--- ----total-cpu-usage---- -dsk/total- vda- -net/total- ------memory-usage----- ---paging-- ---system--')
#     print('         time          | 1m   5m  15m |usr sys idl wai hiq siq| read  writ|util| recv  send| used  buff  cach  free|  in   out | int   csw')

class Dstat:
    def __init__(self):
        self.header_interval = shutil.get_terminal_size(fallback=(80, 25)).lines - 3
        self.stats = [
            Time(),
            LoadAvg(),
            CpuUsage(),
            DiskStats(),
            NetStats(),
            MemUsage(),
        ]
        self.next_due = time.time() + 1
        self.i = 0

    def run(self):
        self.i = 0
        while True:
            time.sleep(max(0, self.next_due - time.time()))
            self.next_due = self.next_due + 1
            if self.i % self.header_interval == 0:
                self.print_header()
            self.print_stats_line()
            self.i += 1

    def print_header(self):
        print(' '.join(stat.header0() for stat in self.stats))
        print('|'.join(stat.header1() for stat in self.stats))

    def print_stats_line(self):
        print('|'.join(stat.value() for stat in self.stats))

def main(argv=None):
    argv = argv or sys.argv
    arg_parser = argparse.ArgumentParser(
            prog=os.path.basename(argv[0]),
            description='dstat.py - psutil version of dstat',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args = arg_parser.parse_args(args=argv[1:])

    signal.signal(signal.SIGQUIT, lambda s,f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s,f: sys.exit(0))

    Dstat().run()

if __name__ == '__main__':
    sys.exit(main())
