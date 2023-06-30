# SMART stats on Cacti (via SNMP)

## Being SMART

Self Monitoring, Analysis, and Reporting Technology is contained in most hard drives these days. It provides a number of built in tests to evaluate the health of a drive and hopefully predict many failures.

Linux has a suite of tools called "smartmontools" which provides a comprehensive set of utilities and a monitoring daemon for checking drives. Configuration of regular testing and monitoring (smartd) is beyond this article and there are plenty of docs around for that already, but what is often useful is to graph key parameters to spot anomalies with parameters which would otherwise go unnoticed.

After installing smartmontools, you can check the basic parameters that drives have with the command:

```sh
smartctl -a DEVICE
```

Where DEVICE is the device for the drive (not a partition). Typically this would be something like /dev/sda (first drive), /dev/sdb (second drive) etc. or /dev/hda (first drive), /dev/hdb (second drive), or some combination of both.

If a drive does not have SMART enabled it will say that in the output of the above. To enable SMART on the drive:

```sh
smartctl -s on DEVICE
```

Note that USB drives do not currently allow SMART data, even though the physical drives inside the boxes are SMART capable. I have no idea why this is the case, and USB drives are the ones I would really like to monitor as they get bashed about more and have poor cooling compared to fixed drives in a system.

## Getting SMART over SNMP

SMART data requires root privilege to access, and snmpd runs as a low privilege user. What I do is have a CRON job (every 5 minutes or to match Cacti polling) that reads this data and stores it in files for snmpd to access via extension scripts.

This code in **smart-cron** simply runs through devices matching /dev/sd? (ie. /dev/sda, /dev/sdb etc.) and dumps their SMART data to a file in **/var/local/snmp/** as described previously.  From here extension scripts for snmpd can pick it up without requiring privilege.

A special case here is if you have a situation where devices get re-ordered on boot (eg. two controllers which may be detected in different order) and you need to force an fixed ordering. Edit smart-cron and uncomment the SMARTLIST variable, and add in all the device paths that will not change (suggest using /dev/disk/by-id/\*). You should go clear out any smart-* files in **/var/local/snmp/** if they have already been created or if you change config to avoid invalid data being left behind.

At this point **STOP**. Wait for the smart-* files to be created in **/var/local/snmp/**. I suspect a lot of problems reported relate to not getting an early part of the chain working fully before moving on. Don't move on until the files exists.

SMART parameters are numbered and it made sense to me to exploit the numbering in a universal script instead of having to treat each parameter on it's own.

I place the parameter parsing script **smart\_generic.py** (make it executable first: chmod +x smart\_generic.py) in **/etc/snmp/**

This script takes one argument of the SMART parameter number and outputs the difference (remaining life) between the current value and the threshold for that parameter. It is worth noting that different manufacturers (and even different models and revisions of drives) create these values differently so the value is of little interest on it's own, but unusual fluctuations or downward trends are worth taking note of. For temperatures it is normally necessary to take the raw data which can be done by prefixing the parameter ID with a 'r'.

This is another good time to **STOP**. Test that the **smart\_generic.py** script is actually picking up the data:

```sh
/etc/snmp/smart_generic.py 1
```

In **/etc/snmp/snmpd.conf** add the lines (or others if you want to monitor them) from snmpd.conf.cacti-smart.

There are many other parameters which you could also monitor and as can be seen, they are easily added by simply referencing the parameter ID and updating templates to match.

Note that the config presented here only looks at /dev/sd? devices. If your system has **/dev/hd?** or **/dev/vd?** devices then you will need to modify the scripts accordingly.

Once you have added all this restart snmpd.

This is another good point to **STOP**. You can test smart-generic by running it from the command line with appropriate parameters, and via SNMP by appending the appropriate SNMP OID to the "snmpwalk" commands shown in previous articles. Ensure that you get valid output on "snmp" related fields when you walk the extended OID: NET-SNMP-EXTEND-MIB::nsExtendOutLine

## Cacti Templates

I have generated some basic Cacti Templates for these SMART parameters with one graph for temperatures and another for health parameters. They are easily extended for more parameters.

For indexed SNMP, Cacti requires an XML file describing how to map the SNMP data to each drive. As this is a local (unpackaged) version I have done my configuration around putting this file in /usr/local/share/cacti/resource/snmp_queries/ and you will need to alter the templates if you put the file elsewhere.

Put the data query XML **disk_smart.xml** in /usr/local/share/cacti/resource/snmp_queries/ or wherever appropriate for your system. Note that if you change the location then you will also need to update the path to this file in the Cacti Data Query for this template.

Simply import the Cacti template **cacti_host_template_smart_parameters.xml**, and add the data query to the hosts you want to monitor then you should see disks available to monitor and be able to add graphs you want in Cacti. It should just work if your SNMP is working correctly for that device (ensure other SNMP parameters are working for that device).

## SSD Support

The big improvement as of version 20121214 is that there are a load of new parameters and templates to support for SSDs. While HDDs have mostly the same stuff from model to model and make to make, every SSD manufacturer has their own ideas on what SMART parameters matter, and that's not surprising since the chipsets are also very different.

I have provided a generic SSD template with everything that seemed to matter on the SSDs I've encountered, but if you use this template directly then you will end up with loads of nan values. The idea is that you can duplicate this template and then prune that down for the specific model of SSD you are monitoring. I have done this for OCZ Agility-3 and Samsung 830 series devices, but you are free to do this for whatever model you have.

## NVME Support

With version 20230630 we also have NVME support. These behave a bit different since there are not lots of individual parameters, but rather a few main health indicators.

## Scaling / normalisation

In many cases different manufacturers (and sometimes even models) have different starting values and thresholds for their parameters. As of version 20121214, the smart\_generic.py script assumes that all parameters start at 100 (mostly the case) and scales them to an graph value of zero at the threshold.

This is however not always the case. Typically a few parameters on most drives may have a different starting or normal value so there is a yaml configuration file that can be used to provide adjustments to the "perfect" starting values. Copy the **smart\_generic.yaml** file into /etc/snmp/ and update as needed.

There are main groups of parameters under the key **parameter\_groups** and these then nave a name for the group and parameters with the related "perfect" starting values.

Then you can apply the groups based on identified family with the **by\_family** mapping or based on identified models with the **by\_model** mapping. Sometimes it's also useful to have pattern matching so the **by\_model\_starts** mapping provides a way of matching by the start of the identified model.


