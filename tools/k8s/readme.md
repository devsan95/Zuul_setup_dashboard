# README

## Environment
### `pyvenv_init.sh`
To setup the environment, use:
```bash
source pyvenv_init.sh
```

This action will create a python 2.7 virtual env and activate it.
Each time you need this env, you should rerun this command.

When you want to deactivate this env, use:
```bash
source deactivate
```

You need internet to complete environment setup. 
So prepare the proxy first.

### Config File
Before creating tickets, you need to 
write down your gerrit settings in config file.
First, you will need a default config file. To create 
it, type:
```bash
python zuul_repo_test.py init-config
```
The script will generate `repo-config.yml`. 
Edit it to what you want.

## Usage
### Optional Parameters
Optional parameters should come before operation. Some operation don't use optional parameters (e.g. `init-config`)
#### `--count [COUNT], -n [COUNT]`
Set the count of ticket to create. Default is 3.
#### `--work-path [WORK_PATH], -p [WORK_PATH]`
Set the work path to clone the repositories. Default is current directory.
#### `--config-file [CONFIG_PATH], -c [CONFIG_PATH]`
Set config file path. Default is `./repo-config.yml`
#### `--with-dependency, -d`
If you use this, tickets will break into groups.
Tickets in one group will have `Depends-On: ` to previous commit.
#### `--with-return-code [{pass,faulty,random,none}], -r [{pass,faulty,random,none}]`
##### pass
Each commit will append a `0`
##### faulty
Each commit will append a `0`, except one will append a `1`
##### random
Each commit will append `0` or `1` randomly.
##### none
Won't append a return code
#### `--reset, -e` 
Perform a reset after each commit to prevent from dependency.
#### `--multiple-files, -m`  
Use multiple files instead of multiple lines. Each push will create push to a new file.
### Operation
#### init-config 
Generate default config to edit
#### one-module 
Create tickets within one module
#### one-repository 
Create tickets within one repository
#### multiple-repositories
Create tickets in multiple repositories
#### gerrit              
Operate the gerrit tickets.
##### abandon             
Abandon all open tickets
##### submit              
Submit all submittable tickets
##### label               
Set label to all open tickets
```
usage: zuul_repo_test.py gerrit label label-name label-value
positional arguments:
label-name   name of the label you want to set
label-value  value of the label you want to set
```
### Example
```bash
python zuul_repo_test.py --count 20 -r faulty -m -e one-module
```
Randomly choose a module from a random repo, and create new files to append lines to create 20 non-conflict tickets based on master.
Last line of each changed file is return code, and one of them is `1` and the others are `0`.

```bash
python zuul_repo_test.py --count 20 -r pass one-module
```
Randomly choose a module from a random repo, and append lines in exist file to create 20 tickets based on preivous commit.
Last line of each changed file is return code, and all of them are `0`

```bash
python zuul_repo_test.py --count 20 -m -e multiple-repositories
```
Create new files to append lines to create 20 non-conflict tickets based on master. The ticket can be in any modules in any repos and may have a depends-on on other tickets.
There are no return code.

