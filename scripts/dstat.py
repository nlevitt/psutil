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
    'lightgrey': '\033[0;37m',
    'darkgrey': '\033[0;90m',
    'reset': '\033[0;0m',
    'underline': '\033[4m',
    'bold': '\033[1m',
}
BLUE = ANSI_ESCAPES['blue']
RESET = ANSI_ESCAPES['reset']
BOLD = ANSI_ESCAPES['bold']
UNDERLINE = ANSI_ESCAPES['underline']
DARKGREY = ANSI_ESCAPES['darkgrey']

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
        if self.value == 0: # int or float
            value_str = ' ' * (self.value_width - 1) + '0'
        elif isinstance(self.value, int):
            value_str = '% *d' % (self.value_width, self.value)
        else:
            value_str = ('%.6f' % self.value)[:self.value_width]
        result = HEAT_COLORS[self.heat_level()] + BOLD + value_str \
                + RESET + DARKGREY + BOLD + self.unit + RESET
        return result

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
        return ('         time          ',)
    def value(self):
        return DARKGREY + datetime.datetime.now().isoformat(timespec='milliseconds') + RESET

class LoadAvg(Statistic):
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

class LoadAvgs:
    def header0(self):
        return '---load-avg---'
    def header1(self):
        return ' 1m ', ' 5m ', ' 15m'
    def value(self):
        loads = (LoadAvg(load).to_str() for load in psutil.getloadavg())
        return ' '.join(loads)

class CpuTime(Statistic):
    def __init__(self, name, value):
        self.name = name
        super().__init__(value, unit='', width=3)

    def heat_level(self):
        if self.name == 'idle':
            return 0
        elif self.value < 5:
            return 0
        elif self.value < 15:
            return 1
        elif self.value < 35:
            return 2
        elif self.value < 70:
            return 3
        else:
            return 4

    def to_str(self):
        if self.value == 0:
            return BOLD + HEAT_COLORS[0] + '0.0' + RESET
        else:
            return super().to_str()

class CpuTimes:
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
        self._header1 = [self.ABBRS[f] for f in cputimes._fields]
        space_to_fill = 4 * len(self._header1) - 1 - len('total-cpu-usage')
        self._header0 = '-' * (space_to_fill // 2) + 'total-cpu-usage' + '-' * (space_to_fill // 2)

    def header0(self):
        return self._header0

    def header1(self):
        return self._header1

    def value(self):
        cputimes = psutil.cpu_times_percent()
        formatted_cputimes = (
                CpuTime(name, value).to_str()
                for name, value in cputimes._asdict().items())
        result = ' '.join(formatted_cputimes)
        return result

# def pretty_bytes(value, width=None, b=' '):
def pretty_bytes(value, b=' '):
    '''
    Returns tuple (value, unit)
    '''
    number = value
    for unit in [b, 'k', 'm', 'g', 't', 'p']:
        if number < 1024.0 or unit == 'p':
            break
        number /= 1024.0
    # if value == 0:
    #     number = '0'
    # else:
    #     number = '%.1f' % value
    # if width:
    #     number = number[:width-1]
    #     if len(number) + 1 < width:
    #         number = ' ' * (width - len(number) - 1) + number
    return number, unit

class DiskStat(Statistic):
    def __init__(self, value):
        number, unit = pretty_bytes(value)
        super().__init__(number, unit=unit, width=5)

    def heat_level(self):
        return 0

class DiskStats:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.disk_io_counters()

    def header0(self):
        return '-dsk/total-'

    def header1(self):
        return ' read', ' writ'

    def value(self):
        t = time.time()
        values = psutil.disk_io_counters()

        elapsed = t - self.last_time
        read_bytes = values.read_bytes - self.last_values.read_bytes
        write_bytes = values.write_bytes - self.last_values.write_bytes

        result = DiskStat(read_bytes / elapsed).to_str() \
                + ' ' + DiskStat(write_bytes / elapsed).to_str()

        self.last_time = t
        self.last_values = values

        return result

class NetStat(Statistic):
    def __init__(self, value):
        number, unit = pretty_bytes(value)
        super().__init__(number, unit=unit, width=5)

    def heat_level(self):
        return 0

class NetStats:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.net_io_counters()

    def header0(self):
        return '-net/total-'

    def header1(self):
        return ' recv', ' send'

    def value(self):
        t = time.time()
        values = psutil.net_io_counters()

        elapsed = t - self.last_time
        bytes_recv = values.bytes_recv - self.last_values.bytes_recv
        bytes_sent = values.bytes_sent - self.last_values.bytes_sent

        result = NetStat(bytes_recv / elapsed).to_str() \
                + ' ' + NetStat(bytes_sent / elapsed).to_str()

        self.last_time = t
        self.last_values = values

        return result

class MemUsage(Statistic):
    def __init__(self, value):
        number, unit = pretty_bytes(value)
        super().__init__(number, unit=unit, width=5)

    def heat_level(self):
        return 0

class MemUsages:
    # TODO add support for buff/cached (not available on mac)

    def header0(self):
        return '-mem-usage-'

    def header1(self):
        return ' used', ' free'

    def value(self):
        vm = psutil.virtual_memory()
        return MemUsage(vm.used).to_str() + ' ' + MemUsage(vm.available).to_str()

class PagingStat(Statistic):
    def __init__(self, value):
        number, unit = pretty_bytes(value)
        super().__init__(number, unit=unit, width=5)

    def heat_level(self):
        return 0

class Paging:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.swap_memory()

    def header0(self):
        return '---paging--'

    def header1(self):
        return '  in ', '  out '

    def value(self):
        t = time.time()
        values = psutil.swap_memory()

        elapsed = t - self.last_time
        sin = values.sin - self.last_values.sin
        sout = values.sout - self.last_values.sout

        result = PagingStat(sin / elapsed).to_str() \
                + ' ' + PagingStat(sout / elapsed).to_str()

        self.last_values = values

        return result

class System:
    def __init__(self):
        self.last_time = time.time()
        self.last_values = psutil.cpu_stats()

    def header0(self):
        return '---system--'

    def header1(self):
        return ' int ', ' csw '

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

class Dstat:
    def __init__(self):
        self.header_interval = shutil.get_terminal_size(fallback=(80, 25)).lines - 3
        self.stats = [
            Time(),
            LoadAvgs(),
            CpuTimes(),
            DiskStats(),
            NetStats(),
            MemUsages(),
            Paging(),
            # System(),
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
                time.sleep(max(0, next_due - time.time()))
                if time.time() - next_due < 0.1:
                    break
            missed_ticks = next_i - (i + 1)
            i = next_i

    COLUMN_DELIM = BLUE + '|' + RESET
    def print_header(self):
        header0 = BLUE + ' '.join(stat.header0() for stat in self.stats) + RESET

        substat_delim = RESET + ' ' + BLUE + UNDERLINE + BOLD
        header1 = Dstat.COLUMN_DELIM.join(
                (BLUE + UNDERLINE + BOLD + substat_delim.join(stat.header1()) + RESET)
                for stat in self.stats)

        print(header0)
        print(header1)

    def print_stats_line(self, missed_ticks):
        line = Dstat.COLUMN_DELIM.join(stat.value() for stat in self.stats)
        if missed_ticks == 1:
            line += ' missed 1 tick'
        elif missed_ticks > 1:
            line += ' missed %s ticks' % missed_ticks
        print(line)

# def term_has_color():
#     "Return whether the system can use colors or not"
#     if sys.stdout.isatty():
#         try:
#             import curses
#             curses.setupterm()
#             if curses.tigetnum('colors') < 0:
#                 return False
#         except ImportError:
#             print('Color support is disabled as python-curses is not installed.', file=sys.stderr)
#             return False
#         except:
#             print('Color support is disabled as curses does not find terminal "%s".' % os.getenv('TERM'), file=sys.stderr)
#             return False
#         return True
#     return False

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
