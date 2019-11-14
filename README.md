# ovirtvmbackup
ovirt rhv agentless vm backup

yum install -y epel-release
yum install -y http://resources.ovirt.org/pub/yum-repo/ovirt-release43.rpm 

yum install -y qemu-img python-ovirt-engine-sdk4 python-requests git ovirt-guest-agent
yum install -y ovirt-imageio-common

backup:
./ovirtvmbackup.py --engine-url https://engine.localdomain --username admin@internal --password-file pass.txt -c ca.crt --backup-dir /data/backup winxp

more  pass.txt
password

restore disk:
./upload_disk.py --engine-url https://engine.localdomain --username admin@internal -file pass.txt --disk-format qcow2  --sd-name iscsilvm -c ca.crt /data/backup/winxp/20191114142105/winxpclone_Disk1-f75ba2a0-f7e5-477b-bb3d-38acbce8f4fc

restore ovf:
edit add_vm_from_ovf.py set correct connection = sdk.Connection,ovf_file_path
./add_vm_from_ovf.py

on engine web admin:
attach the disk and boot vm.

ok!
————————————————
版权声明：本文为CSDN博主「allway2」的原创文章，遵循 CC 4.0 BY-SA 版权协议，转载请附上原文出处链接及本声明。
原文链接：https://blog.csdn.net/allway2/article/details/102994798

以上脚本使用磁盘映像传输API实现备份，为保证备份为全备份，在备份开始前删除了要备份虚拟机上以前存在的所有快照。

该API出现在oVirt / RHV 4.2中，并允许直接从RHV管理器导出单个快照。因此，现在，您不必安装多个代理VM，而只需安装一个外部Node，即可通过RHV管理器调用API。

此策略支持增量备份。假设您拥有oVirt / RHV 4.2或更高版本–只需将您的管理器添加到vProtect即可完成设置。从网络角度来看-它需要另外两个端口才能打开54322和54323，并且您的数据将从虚拟机管理程序管理器中提取。

不幸的是，该解决方案的当前体系结构几乎没有问题。最大的问题是所有流量都通过oVirt / RHV管理器传递，这可能会影响您在备份过程中可以达到的传输速率。
————————————————
版权声明：本文为CSDN博主「allway2」的原创文章，遵循 CC 4.0 BY-SA 版权协议，转载请附上原文出处链接及本声明。
原文链接：https://blog.csdn.net/allway2/article/details/103012006
