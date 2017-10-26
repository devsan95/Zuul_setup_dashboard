# Readme

## Initialize environment
### Python
1. Make sure that http and https proxy are set properly.
2. Enter `mn_scripts` directory.
3. Run `source pyenv.sh`.
4. If `(python2)` appears in front of the command line, the initialization is ready.

When you want to deactivate this env, use:
```bash
source deactivate
```

## Tool Scripts
### `layout_handler.py`
This script is for merging and checking layout snippet files. 
To check layout snippets, it searches for duplicated projects and jobs in different files, 
 and verifies all jobs match the rule: jobs must correspond to projects in the same file,
 and mustn't match projects in other files. We set this rule for we think jobs should not effect projects in other place.

To use this script, some parameters must be input first:
>`--zuul-config [ZUUL_CONFIG]` or in short `-z [ZUUL_CONFIG]`
>
>Specify the path of zuul.conf file. The script need the connection
>names in the conf file to verify connections in layout files.
>
>`--input-file [INPUT_FILE]` or in short `-i [INPUT_FILE]`
>
>Path ot main file of layout snippets, usually it is `layout.yaml` with `layout.d` in one directory.

There are four sub-commands in this script:
#### verify
Verify a complete `layout.yaml` file (not snippets) with zuul internal checks.
Example:
```bash
python layout_handler.py -i path/to/complete/layout/layout.yaml -z /path/to/zuul.conf verify
```
If everything is OK, it returns 0. Otherwise, check the prompts.
#### merge
Merge snippets into one. Before and After merging, some checks take place.

There is a parameter for this sub-command:
>`--output-file [OUTPUT_FILE]` or in short `-o [OUTPUT_FILE]`
>
> Path to place merged layout. If path exists, the old
> file will be archived. 
>
>If this parameter is not given, there will be no output file. You can do merely checks this way.

Examples:
```bash
python layout_handler.py -i path/to/complete/layout/layout.yaml -z /path/to/zuul.conf merge -o /path/to/output/layout.yaml
```
If everything is OK, it returns 0. Otherwise, check the prompts.
#### check
Merge and check a snippet with main layout file. The merging is just for checking, so there are no output files.
There is a parameter for this sub-command:
>`--input-snippet [SNIPPET]` or in short `-s [SNIPPET]`
>
>Path of the snippet to check.

Examples:
```bash
python layout_handler.py -i path/to/complete/layout/layout.yaml -z /path/to/zuul.conf check -s /path/to/input/snippet.yaml
```
If everything is OK, it returns 0. Otherwise, check the prompts.

### `zuul_repo_test.py`
#### Config File
Before creating tickets, you need to 
write down your gerrit settings in config file.
First, you will need a default config file. To create 
it, type:
```bash
python zuul_repo_test.py init-config
```
The script will generate `repo-config.yml`. 
Edit it to what you want.

#### Usage
##### Optional Parameters
Optional parameters should come before operation. Some operation don't use optional parameters (e.g. `init-config`)
- `--count [COUNT], -n [COUNT]`
Set the count of ticket to create. Default is 3.
- `--work-path [WORK_PATH], -p [WORK_PATH]`
Set the work path to clone the repositories. Default is current directory.
- `--config-file [CONFIG_PATH], -c [CONFIG_PATH]`
Set config file path. Default is `./repo-config.yml`
- `--with-dependency, -d`
If you use this, tickets will break into groups.
Tickets in one group will have `Depends-On: ` to previous commit.
- `--with-return-code [{pass,faulty,random,none}], -r [{pass,faulty,random,none}]`
    - `pass`
    Each commit will append a `0`
    - `faulty`
    Each commit will append a `0`, except one will append a `1`
    - `random`
    Each commit will append `0` or `1` randomly.
    - `none`
    Won't append a return code
- `--reset, -e` 
Perform a reset after each commit to prevent from dependency.
- `--multiple-files, -m`  
Use multiple files instead of multiple lines. Each push will create push to a new file.
##### Operation
- init-config 
Generate default config to edit
- one-module 
Create tickets within one module
- one-repository 
Create tickets within one repository
- multiple-repositories
Create tickets in multiple repositories
- gerrit              
Operate the gerrit tickets.
    - abandon             
    Abandon all open tickets
    - submit              
    Submit all submittable tickets
    - label               
    Set label to all open tickets
        ```
        usage: zuul_repo_test.py gerrit label label-name label-value
        positional arguments:
        label-name   name of the label you want to set
        label-value  value of the label you want to set
        ```
#### Example
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

