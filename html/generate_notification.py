import click
import cgi
import arrow
import subprocess
from api import gerrit_rest
import codecs
import ruamel.yaml as yaml
from slugify import slugify


template = u"""
   <div class="alert alert-{alert_type}" role="alert">
           <div style="display: flex;flex-direction: row;">
                   <div class="col-1 alert-icon-col" style="float:left;margin-right:10px;">
                       <span class="glyphicon {icon}"></span>
                   </div>
                   <div class="col">
                           <h4 class="alert-heading">{title} {label}</h4>
                           <p>{content}</p>
                           <p style="margin-top:15px;margin-bottom:-5px">
                                <span class="glyphicon glyphicon-user"></span> {author}
                                <span> </span>
                                <span class="glyphicon glyphicon-time"></span>
                                <span id="{date_id}"></span>
                                <script>
                                    var update_time = new Date({time});
                                    $('#{date_id}').html(update_time.toString());
                                </script>
                           </p>
                   </div>
           </div>
   </div>
       """


def generate_html(notification, history_no=None):
    date_id = 'notification_date_span'
    if history_no is not None:
        date_id += str(history_no)
    content_line = '<br />'.join(notification['content'].split('\n'))
    label_template = '<span class="label label-{type}">{label}</span>'
    label_line = ''
    if notification['label']:
        label_line = label_template.format(type=notification['label_type'], label=notification['label'])

    output = template.format(alert_type=notification['alert_type'],
                             icon=notification['icon'],
                             title=notification['title'],
                             label=label_line, content=content_line,
                             author=notification['author'],
                             time=notification['timestamp'],
                             date_id=date_id)
    output = codecs.encode(output, 'utf-8')

    return output


@click.command()
@click.option('--title', required=True)
@click.option('--content', required=True)
@click.option('--author', required=True)
@click.option('--alert-type', type=click.Choice(['success', 'info', 'warning', 'danger']), default='info')
@click.option('--icon', default='glyphicon-info-sign')
@click.option('--label', default=None)
@click.option('--label-type', type=click.Choice(['default', 'primary', 'success', 'info', 'warning', 'danger']),
              default='default')
@click.option('--gerrit-available', default=True, type=bool)
@click.option('--gerrit-path', default=None)
@click.option('--zuul-server-name', required=True)
@click.option('--project', default=None)
@click.option('--branch', default=None)
@click.option('--file-path', default=None)
@click.option('--history-path', default=None)
@click.option('--list-path', default=None)
@click.option('--archiving-path', default=None)
@click.option('--history-count', default=3)
@click.option('--archiving-threshold', default=100)
def main(title, content, author, alert_type, icon, label, label_type,
         gerrit_path, zuul_server_name, gerrit_available, project, branch, file_path, history_path, list_path,
         archiving_path, history_count, archiving_threshold):
    title = cgi.escape(title)
    content = cgi.escape(content)
    author = cgi.escape(author)
    alert_type = cgi.escape(alert_type)
    icon = cgi.escape(icon)
    label = cgi.escape(label)
    label_type = cgi.escape(label_type)
    zuul_server_name = cgi.escape(zuul_server_name)
    show_in_history = False

    if title:
        # set notification dict
        current_notification = {
            'title': title,
            'alert_type': alert_type,
            'icon': icon,
            'label': label,
            'label_type': label_type,
            'content': content,
            'author': author,
            'timestamp': arrow.utcnow().timestamp * 1000,
        }
        # set notification
        output = generate_html(current_notification)
    else:
        current_notification = {
            'title': "Clear Notification",
            'alert_type': "info",
            'icon': "glyphicon-cog",
            'label': "Clear",
            'label_type': "info",
            'content': "Previous content is cleared.",
            'author': author,
            'timestamp': arrow.utcnow().timestamp * 1000,
        }
        output = ""
        show_in_history = True

    print("DEBUG_INFO: main: Output is: {}".format(output))

    # copy list.yaml from docker container
    subprocess.check_call("rm -rf origin_notification notification_changed;mkdir origin_notification notification_changed;"
                          "docker cp {}:/ephemeral/zuul/www/notification/list.yaml origin_notification/".format(zuul_server_name), shell=True)
    print("DEBUG_INFO: main: copy list.yaml from docker container success!")

    if gerrit_available:
        print("DEBUG_INFO: main: gerrit is available")
        rest = None
        if gerrit_path:
            rest = gerrit_rest.init_from_yaml(gerrit_path)

        if rest:
            if output:
                commit_msg = u'Update Notification [{}] by [{}]'.format(title, author)
            else:
                commit_msg = 'Clear Notification by [{}]'.format(author)
            change_id, ticket_id, rest_id = rest.create_ticket(project, None, branch, commit_msg)
            print("DEBUG_INFO: main: crete ticket finished.")
            print("DEBUG_INFO: main: change_id: {}, ticket_id: {}, rest_id: {}".format(change_id, ticket_id, rest_id))

            update_history(current_dict=current_notification,
                           rest=rest,
                           change_no=change_id,
                           history_path=history_path,
                           list_path=list_path,
                           archiving_path=archiving_path,
                           history_count=history_count,
                           archiving_threshold=archiving_threshold,
                           show_in_history=show_in_history,
                           merge_conflict=False)
            try:
                print("DEBUG_INFO: main: push file to change and submit")
                rest.add_file_to_change(change_id, file_path, output)
                rest.publish_edit(change_id)
                rest.review_ticket(change_id,
                                   codecs.encode(u'Author is {}'.format(author), 'utf-8'),
                                   {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
                rest.submit_change(change_id)
                print("DEBUG_INFO: main: push file to change and submit finished!")
                # result = zuul_server_container.exec_run(cmd="cd /ephemeral/zuul/www/notification/;git reset --hard HEAD;git pull")
                update_git_repo(zuul_server_name=zuul_server_name, branch=branch)
            except Exception as e:
                print("DEBUG_INFO: main: submit with merge_conflict=False failed!")
                print("DEBUG_INFO: main: set merge_conflict=True, and retry with push file to change and submit")
                rest.abandon_change(change_id)
                print("DEBUG_INFO: main: change {} has been abandoned!".format(change_id))
                new_change_id, new_ticket_id, new_rest_id = rest.create_ticket(project, None, branch, commit_msg)
                print("DEBUG_INFO: main: new change created, change_id: {}, ticket_id: {}, rest_id: {}".format(new_change_id, new_ticket_id, new_rest_id))

                update_history(current_dict=current_notification,
                               rest=rest,
                               change_no=new_change_id,
                               history_path=history_path,
                               list_path=list_path,
                               archiving_path=archiving_path,
                               history_count=history_count,
                               archiving_threshold=archiving_threshold,
                               show_in_history=show_in_history,
                               merge_conflict=True)
                try:
                    rest.add_file_to_change(new_change_id, file_path, output)
                    rest.publish_edit(new_change_id)
                    rest.review_ticket(new_change_id, codecs.encode(u'Author is {}'.format(author), 'utf-8'),
                                       {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
                    rest.submit_change(new_change_id)
                    print("DEBUG_INFO: main: retry with merge_conflict=True, push file to change and submit finished!")
                    update_git_repo(zuul_server_name=zuul_server_name, branch=branch)
                except Exception as e:
                    rest.abandon_change(new_change_id)
                    print("DEBUG_INFO: main: change {} has been abandoned!".format(new_change_id))
                    raise e
    else:
        print("DEBUG_INFO: main: Gerrit is not available!")
        # get content from list.yaml
        # file address need to be more accurate
        with open("origin_notification/list.yaml", 'r') as f:
            list_yaml = f.read()
        list_list = yaml.load(list_yaml, Loader=yaml.Loader, version='1.1')

        history_str, list_save, list_archiving = get_file_contents(current_dict=current_notification,
                                                                   show_in_history=show_in_history,
                                                                   list_yaml=list_list,
                                                                   history_count=history_count,
                                                                   archiving_path=archiving_path,
                                                                   archiving_threshold=archiving_threshold)

        list_save_yaml = yaml.dump(list_save, Dumper=yaml.RoundTripDumper)

        # create changed files
        create_changed_file(data_str=list_save_yaml, changed_file_name="list.yaml")
        create_changed_file(data_str=output, changed_file_name="index.html")
        create_changed_file(data_str=history_str, changed_file_name="history.html")

        # put list.yaml index.html history.html to docker container
        subprocess.check_call("docker cp ./notification_changed/. {}:/ephemeral/zuul/www/notification/".format(zuul_server_name), shell=True)
        print("DEBUG_INFO: main: Copy files into container success!")


def create_changed_file(data_str, changed_file_name):
    print("DEBUG_INFO: create_changed_file: {} start!".format(changed_file_name))
    with open("notification_changed/{}".format(changed_file_name), 'w') as f:
        f.writelines(data_str)
    print("DEBUG_INFO: create_changed_file: {} end!".format(changed_file_name))


def get_file_contents(current_dict, show_in_history, list_yaml, history_count, archiving_path, archiving_threshold):
    print("DEBUG_INFO: get_file_contents: start!")
    # add history list
    if show_in_history:
        if current_dict:
            list_yaml.insert(0, current_dict)
    # set history
    history_str = ""
    history_show = history_count
    if history_show > len(list_yaml):
        history_show = len(list_yaml)
    for i in range(0, history_show):
        history_str += generate_html(list_yaml[i], history_no=i)
    # add history list
    if not show_in_history:
        if current_dict:
            list_yaml.insert(0, current_dict)
    # archiving
    list_save = list_yaml[:]
    list_archiving = []
    if archiving_path:
        if len(list_yaml) >= history_count + archiving_threshold:
            list_save = list_yaml[:history_count]
            list_archiving = list_yaml[history_count:]
    print("DEBUG_INFO: get_file_contents: end!")
    return history_str, list_save, list_archiving


def add_files_to_change(history_path, history_str, list_save, rest, change_no,
                        list_path, list_archiving, archiving_path):
    print("DEBUG_INFO: add_files_to_change: start!")
    if history_path:
        rest.add_file_to_change(change_no, history_path, history_str)
        print("DEBUG_INFO: add_files_to_change: add history to change finished!")
    if list_save:
        list_save_yaml = yaml.dump(list_save, Dumper=yaml.RoundTripDumper)
        rest.add_file_to_change(change_no, list_path, list_save_yaml)
        print("DEBUG_INFO: add_files_to_change: add list yaml to change finished!")
    if list_archiving:
        list_archiving_yaml = yaml.dump(list_archiving, Dumper=yaml.RoundTripDumper)
        archiving_path = archiving_path + slugify(arrow.now().isoformat()) + '.yaml'
        rest.add_file_to_change(change_no, archiving_path, list_archiving_yaml)
        print("DEBUG_INFO: add_files_to_change: add list archiving to change finished!")
    print("DEBUG_INFO: add_files_to_change: end!")


def update_git_repo(zuul_server_name, branch):
    print("DEBUG_INFO: update_git_repo: start!")
    result = subprocess.call(
        'docker exec {} bash -c "cd /ephemeral/zuul/www/notification/;git reset --hard HEAD;git checkout {};git pull"'.format(zuul_server_name, branch),
        shell=True)
    if result == 0:
        print("DEBUG_INFO: update_git_repo: update notification REPO in container")
    else:
        print("DEBUG_INFO: update_git_repo: update notification REPO in container failed!")
        raise Exception("update notification REPO in container failed")
    print("DEBUG_INFO: update_git_repo: end!")


def update_history(current_dict, rest, change_no, history_path, list_path,
                   archiving_path, history_count, archiving_threshold,
                   show_in_history, merge_conflict=False):
    print("DEBUG_INFO: update_history: start!")
    if merge_conflict:
        print("DEBUG_INFO: update_history: merge_conflict = True !")
        if not list_path:
            print('No list path')
            return

        list_yaml = rest.get_file_content(list_path, change_no)
        list_list = yaml.load(list_yaml, Loader=yaml.Loader, version='1.1')

        history_str, list_save, list_archiving = get_file_contents(current_dict=current_dict,
                                                                   show_in_history=show_in_history,
                                                                   list_yaml=list_list,
                                                                   history_count=history_count,
                                                                   archiving_threshold=archiving_threshold,
                                                                   archiving_path=archiving_path)
        print("DEBUG_INFO: update_history: get file contents finished")
    else:
        print("DEBUG_INFO: update_history: merge_conflict = False !")
        # get content from list.yaml
        with open("origin_notification/list.yaml", 'r') as f:
            list_yaml = f.read()
        list_list = yaml.load(list_yaml, Loader=yaml.Loader, version='1.1')

        history_str, list_save, list_archiving = get_file_contents(current_dict=current_dict,
                                                                   show_in_history=show_in_history,
                                                                   list_yaml=list_list,
                                                                   history_count=history_count,
                                                                   archiving_threshold=archiving_threshold,
                                                                   archiving_path=archiving_path)
        print("DEBUG_INFO: update_history: get file contents finished")
    add_files_to_change(rest=rest,
                        list_path=list_path,
                        history_path=history_path,
                        history_str=history_str,
                        change_no=change_no,
                        archiving_path=archiving_path,
                        list_archiving=list_archiving,
                        list_save=list_save)
    print("DEBUG_INFO: update_history: end!")


if __name__ == '__main__':
    main()
