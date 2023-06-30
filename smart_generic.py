#!/usr/bin/env python3
"""
Copyright (C) 2009-2023 Glen Pitt-Pladdy

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.



See: https://www.pitt-pladdy.com/blog/_20091031-144604_0000_SMART_stats_on_Cacti_via_SNMP_/

Put SMART parameter ID on command line, prefixed by 'R' if you want raw value, or 'W' if you want worst value

Put "worst" on the command line and the smallest gap (worst case) to threshold of all
parameters will be output.

Version 20190810
"""

import os
import glob
import sys
import yaml
import json

STORE = '/var/local/snmp'
PREFIX = 'smart-'
# how should we index/identify devices
INDEX = 'dev'
#INDEX = 'serial'


# see https://www.nvmexpress.org/wp-content/uploads/NVM_Express_1_2b_Gold_20160603.pdf
NVME_GENERIC_THRESHOLDS = {
}


class HealthyParameters(object):
    def __init__(self):
        device_specific_config = os.path.realpath(__file__)
        device_specific_config = os.path.splitext(device_specific_config)[0] + '.yaml'
        self.device_specific = {
            'parameter_groups': {},
            'by_family': {},
            'by_model': {},
            'by_model_starts': {},
        }
        if os.path.isfile(device_specific_config):
            with open(device_specific_config, 'rt') as dev:
                self.device_specific = yaml.safe_load(dev)
        self.parameter_groups = self.device_specific['parameter_groups']

    def lookup(self, smart_data, parameter):
        # determine what parameters apply
        healthy_parameters = {}
        if smart_data['model_family'] in self.device_specific['by_family']:
            healthy_parameters.update(self.parameter_groups[self.device_specific['by_family'][smart_data['model_family']]])
        if smart_data['model_name'] in self.device_specific['by_model']:
            # most specific overrides family
            healthy_parameters.update(self.parameter_groups[self.device_specific['by_model'][smart_data['model_name']]])
        else:
            # search
            for starts_with in self.device_specific['by_model_starts']:
                if smart_data['model_name'].startswith(starts_with):
                    healthy_parameters.update(self.parameter_groups[self.device_specific['by_model_starts'][starts_with]])
                    break
        # lookup specific parameter
        if parameter in healthy_parameters:
            return healthy_parameters[parameter]
        return 100  # default
      

def usage():
    print(f"Usage: {sys.argv[0]} <SMART parameter|devices|description|worst>", file=sys.stderr)
    sys.exit(1)


def main(argv):
    if len(argv) != 2:
        usage()
    if argv[1] in ['devices', 'description', 'devicecount']:
        mode = argv[1]
    elif argv[1] == 'worst':
        mode = 'worst_overall'
    else:
        parameter = argv[1]
        if parameter.startswith('w') and parameter[1:].isdigit():
            mode = 'worst'
            parameter = int(parameter[1:])
        elif parameter.startswith('r') and parameter[1:].isdigit():
            mode = 'raw'
            parameter = int(parameter[1:])
        elif parameter.isdigit() and len(parameter) <= 3:
            mode = 'health'
            parameter = int(parameter)
        elif not parameter.isdigit() and len(parameter) >= 6:
            # named parameters for nvme
            mode = 'named'
        else:
            usage()
    # get list of device smart data files
    smart_data = glob.glob(os.path.join(STORE, PREFIX + '*.json'))
    if mode == 'devicecount':
        # no need to go further
        print(len(smart_data))
        return

    # load each device data
    healthy_parameters = HealthyParameters()
    worst_overall = 255
    for smart_file in sorted(smart_data):
        device_name = os.path.basename(smart_file)
        device_name = os.path.splitext(device_name)[0]
        device_name = device_name[len(PREFIX):]
        if mode == 'devices' and INDEX == 'dev':
            print(device_name)
            continue
        try:
            with open(smart_file, 'rt') as dev:
                smart_data = json.load(dev)
            data_type = None
            if 'nvme_smart_health_information_log' in smart_data:
                data_type = 'nvme_smart_health_information_log'
                table = smart_data[data_type]
            elif 'ata_smart_attributes' in smart_data:
                data_type = 'ata_smart_attributes'
                table = smart_data[data_type]['table']
            elif smart_data.get('smartctl', {}).get('exit_status') != 0:
                smart_data = None
            else:
                raise KeyError(f"Can't find any known key in smart_data for: {smart_file}")
        except json.decoder.JSONDecodeError:
            smart_data = None
        # work out what healthy parameters look like
        # fish out the data we want
        if mode in ['health', 'raw', 'worst']:
            if smart_data is None:
                print('U')
                continue
            if data_type != 'ata_smart_attributes':
                print('U')
                continue
            values = None
            for item in table:
                if item['id'] == parameter:
                    values = item
                    break
            if values is None:
                print('U')
                continue
            if mode == 'health':
                value = values['value'] - values['thresh']
                # TODO handle None healthy
                healthy_value = healthy_parameters.lookup(smart_data, values['id']) - values['thresh']
                value = float(value) / healthy_value * 100
            elif mode == 'raw':
                # parse string since raw is encoded
                value = float(values['raw']['string'].split(None, 1)[0])
                print(value)
                continue
            elif mode == 'worst':
                value = values['worst'] - values['thresh']
                # TODO handle None healthy
                healthy_value = healthy_parameters.lookup(smart_data, values['id']) - values['thresh']
                value = float(value) / healthy_value * 100
            else:
                raise RuntimeError("Mode should have been checked before - bug!")
            # limit the parameter to 101
            print(min(value, 101))
        elif mode == 'named':
            if smart_data is None:
                print('U')
                continue
            if data_type != 'nvme_smart_health_information_log':
                print('U')
                continue
            if parameter.startswith('temperature_sensors_'):
                index = parameter[20:]
                if not index.isdigit():
                    raise ValueError(f"Index not digits: {parameter} => {index}")
                index = int(index)
                if index < 1 or index > 8:
                    raise ValueError(f"Index outside range: 1 <= {index} <= 8")
                parameter = 'temperature_sensors'
            value = table.get(parameter)
            if value is None:
                print('U')
                continue
            # special treatment (normalisation)
            if parameter == 'critical_warning':
                value = 100 if value == 0 else 0
            elif parameter == 'available_spare':
                if 'available_spare_threshold' in table:
                    value -= table['available_spare_threshold']
                    value /= table['available_spare'] - table['available_spare_threshold']
                    value = max(int(value * 100.0), 0)
            elif parameter == 'percentage_used':
                value = 100 - value
                value = max(value, 0)
            elif parameter == 'data_units_written':
                pass    # TODO needs threshold
            elif parameter == 'controller_busy_time':
                pass    # TODO needs history
            elif parameter == 'power_on_hours':
                pass    # TODO needs threshold
            elif parameter == 'media_errors':
                pass    # TODO needs threshold
            elif parameter == 'num_err_log_entries':
                pass    # TODO needs threshold
            elif parameter == 'warning_temp_time':
                pass    # TODO needs history
            elif parameter == 'critical_comp_time':
                pass    # TODO needs threshold TODO needs history
            elif parameter == 'temperature_sensors':
                try:
                    value = value[index - 1]
                except IndexError:
                    print('U')
                    continue
            print(min(value, 101))
        elif mode == 'worst_overall':
            if smart_data is None:
                continue
            for values in table:
                if values['id'] in [190, 194]:
                    # skip temperatures etc. that behave different
                    continue
                value = values['value'] - values['thresh']
                healthy_value = healthy_parameters.lookup(smart_data, values['id']) - values['thresh']
                value = float(value) / healthy_value * 100
                worst_overall = min(worst_overall, value)
        elif mode == 'device' and INDEX == 'serial':
            if smart_data is None:
                print("UNKNOWN")
            else:
                print(smart_data['serial_number'])
        elif mode == 'description':

            description = smart_data['model_name']
            if INDEX == 'dev':
                description += " ({})".format(device_name)
            elif INDEX == 'serial' and smart_data is not None:
                description += " (SN {})".format(smart_data['serial_number'])
            else:
                raise RuntimeError("INDEX not handled - bug!")
            if smart_data is not None:
                description += " [{}]".format(smart_data['firmware_version'])
                capacity_value = smart_data['user_capacity']['bytes']
                capacity_unit = 'B'
                for unit in ['kB','MB','GB','TB','PB']:
                    if capacity_value < 1000:
                        break
                    capacity_value /= 1000
                    capacity_unit = unit
                description += " {} {}".format(capacity_value, capacity_unit)
            print(description.strip())
        else:
            raise RuntimeError("Mode & INDEX should have been checked before - bug!")
    if mode == 'worst_overall':
        print(worst_overall)


if __name__ == '__main__':
    main(sys.argv)
