#!/usr/bin/env python

import sys
import argparse
import os
import time
import datetime
import psutil
import shutil
import signal
import abc

ANSI_ESCAPES = {
    'black': '\033[0;30m',
    'red': '\033[0;31m',
    'green': '\033[0;32m',
    'yellow': '\033[0;33m',
    'blue': '\033[0;34m',
    'magenta': '\033[0;35m',
    'cyan': '\033[0;36m',
    'grey': '\033[0;37m',
    'reset': '\033[0;0m',
}

HEAT_COLORS = [
    ANSI_ESCAPES['blue'],   # (4)
    ANSI_ESCAPES['cyan'],   # (6)
    ANSI_ESCAPES['green'],  # (2)
    ANSI_ESCAPES['yellow'], # (3)
    ANSI_ESCAPES['red'],    # (1)
]

# base class for a single statistic
class Statistic(abc.ABC):
    def __init__(self, value, unit, width):
        self.value = value
        self.unit = unit
        self.width = width
        self.value_width = width - len(unit)

    @abc.abstractmethod
    def heat_level(self):
        '''
        Returns a value between 0 (blue) and 4 (red)
        '''
        raise NotImplementedError

    def to_str(self):
        value_str = ('%.6f' % self.value)[:self.value_width]
        result = HEAT_COLORS[self.heat_level()] + value_str + ANSI_ESCAPES['reset'] + self.unit
        return result

class Load(Statistic):
    def __init__(self, value):
        super().__init__(value, unit='', width=4)

    def heat_level(self):
        # :shrug:
        if self.value < 0.5:
            return 0
        elif self.value < 1:
            return 1
        elif self.value < 2:
            return 2
        elif self.value < 5:
            return 3
        else:
            return 4

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
        loads = (Load(load).to_str() for load in psutil.getloadavg())
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

def pretty_bytes(value, width=None, b=' '):
    for unit in [b, 'k', 'm', 'g', 't', 'p']:
        if value < 1024.0 or unit == 'p':
            break
        value /= 1024.0
    if value == 0:
        number = '0'
    else:
        number = '%.1f' % value
    if width:
        number = number[:width-1]
        if len(number) + 1 < width:
            number = ' ' * (width - len(number) - 1) + number
    return number + unit

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

        read_rate = pretty_bytes(read_bytes / elapsed, 5)
        write_rate = pretty_bytes(write_bytes / elapsed, 5)

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

        recv_rate = pretty_bytes(bytes_recv / elapsed, 5)
        send_rate = pretty_bytes(bytes_sent / elapsed, 5)

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
        return '%s %s' % (
                pretty_bytes(vm.used, 5),
                pretty_bytes(vm.available, 5))

class Paging:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.swap_memory()

    def header0(self):
        return '---paging--'

    def header1(self):
        return '  in   out '

    def value(self):
        t = time.time()
        values = psutil.swap_memory()

        elapsed = t - self.last_time
        sin = values.sin - self.last_values.sin
        sout = values.sout - self.last_values.sout

        sin_rate = pretty_bytes(sin / elapsed, 5)
        sout_rate = pretty_bytes(sout / elapsed, 5)

        result = '%s %s' % (sin_rate, sout_rate)

        self.last_values = values

        return result

class System:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.cpu_stats()

    def header0(self):
        return '---system--'

    def header1(self):
        return ' int   csw'

    def value(self):
        t = time.time()
        values = psutil.cpu_stats()

        elapsed = t - self.last_time
        ctx_switches = values.ctx_switches - self.last_values.ctx_switches
        interrupts = values.interrupts - self.last_values.interrupts

        if psutil.MACOS:
            # not sure what these numbers mean exactly on mac
            # see https://github.com/giampaolo/psutil/issues/847
            # and https://developer.apple.com/documentation/kernel/1502546-host_statistics
            csw_rate = pretty_bytes(values.ctx_switches, 5)
            int_rate = pretty_bytes(values.interrupts, 5)
        else:
            csw_rate = pretty_bytes(ctx_switches / elapsed, 5)
            int_rate = pretty_bytes(interrupts / elapsed, 5)

        result = '%s %s' % (int_rate, csw_rate)

        self.last_values = values

        return result

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
            Paging(),
            System(),
        ]

    def run(self):
        time.sleep(0.2)
        start = time.time()
        row = 0
        i = 0
        missed_ticks = 0
        while True:
            if row % self.header_interval == 0:
                self.print_header()
                row = 0
            self.print_stats_line(missed_ticks)
            row += 1
            while True:
                next_i = int(time.time() - start + 1)
                next_due = start + next_i
                # print("i=%s next_due=%s" % (i, next_due))
                time.sleep(max(0, next_due - time.time()))
                if time.time() - next_due < 0.1:
                    break
            missed_ticks = next_i - (i + 1)
            i = next_i

    def print_header(self):
        print(ANSI_ESCAPES['blue'] + ' '.join(stat.header0() for stat in self.stats) + ANSI_ESCAPES['reset'])
        print(ANSI_ESCAPES['blue'] + '|'.join(stat.header1() for stat in self.stats) + ANSI_ESCAPES['reset'])

    def print_stats_line(self, missed_ticks):
        line = '|'.join(stat.value() for stat in self.stats)
        if missed_ticks == 1:
            line += ' missed 1 tick'
        elif missed_ticks > 1:
            line += ' missed %s ticks' % missed_ticks
        print(line)

def term_has_color():
    "Return whether the system can use colors or not"
    if sys.stdout.isatty():
        try:
            import curses
            curses.setupterm()
            if curses.tigetnum('colors') < 0:
                return False
        except ImportError:
            print('Color support is disabled as python-curses is not installed.', file=sys.stderr)
            return False
        except:
            print('Color support is disabled as curses does not find terminal "%s".' % os.getenv('TERM'), file=sys.stderr)
            return False
        return True
    return False

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
