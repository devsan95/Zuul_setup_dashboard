import click
import cgi
import arrow
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
                           <p style="margin-top:15px;margin-bottom:-5px"><span class="glyphicon glyphicon-user"></span> {author} <span> </span><span class="glyphicon glyphicon-time"></span> <span id="{date_id}"></span><script>var update_time = new Date({time}); $('#{date_id}').html(update_time.toString());</script> </p>
                   </div>
           </div>
   </div>
       """


def generate_html(notification, history_no=None):
    date_id = 'notification_date_span'
    if history_no:
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
@click.option('--label-type', type=click.Choice(['default', 'primary', 'success', 'info', 'warning', 'danger']), default='default')
@click.option('--gerrit-path', default=None)
@click.option('--project', default=None)
@click.option('--branch', default=None)
@click.option('--file-path', default=None)
@click.option('--history-path', default=None)
@click.option('--list-path', default=None)
@click.option('--archiving-path', default=None)
@click.option('--history-count', default=3)
@click.option('--archiving-threshold', default=100)
def main(title, content, author, alert_type, icon, label, label_type,
         gerrit_path, project, branch, file_path, history_path, list_path,
         archiving_path, history_count, archiving_threshold):
    title = cgi.escape(title)
    content = cgi.escape(content)
    author = cgi.escape(author)
    alert_type = cgi.escape(alert_type)
    icon = cgi.escape(icon)
    label = cgi.escape(label)
    label_type = cgi.escape(label_type)

    rest = None
    if gerrit_path:
        rest = gerrit_rest.init_from_yaml(gerrit_path)

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
        output = ""

    print("Output is:")
    print(output)
    if rest:
        if output:
            commit_msg = u'Update Notification [{}]'.format(title)
        else:
            commit_msg = 'Clear Notification'
        change_id, ticket_id, rest_id = rest.create_ticket(project, None, branch, commit_msg)
        if output:
            update_history(current_notification, rest, change_id,
                           history_path, list_path,
                           archiving_path, history_count,
                           archiving_threshold)
        try:
            rest.add_file_to_change(rest_id, file_path, output)
            rest.publish_edit(rest_id)
            rest.review_ticket(rest_id, codecs.encode(u'Author is {}'.format(author), 'utf-8'), {'Code-Review': 2, 'Verified': 1, 'Gatekeeper': 1})
            rest.submit_change(rest_id)
        except Exception as e:
            rest.abandon_change(rest_id)
            raise e


def update_history(current_dict, rest, change_no, history_path, list_path,
                   archiving_path, history_count, archiving_threshold):
    if not list_path:
        print('No list path')
        return

    list_yaml = rest.get_file_content(list_path, change_no)
    list_list = yaml.load(list_yaml, Loader=yaml.Loader, version='1.1')
    # set history
    history_str = ""
    history_show = history_count
    if history_show > len(list_list):
        history_show = len(list_list)
    for i in range(0, history_show):
        history_str += generate_html(list_list[i])
    if history_path:
        rest.add_file_to_change(change_no, history_path, history_str)
    # add history list
    list_list.insert(0, current_dict)
    # archiving
    list_save = list_list[:]
    list_archiving = []
    if archiving_path:
        if len(list_list) >= history_count + archiving_threshold:
            list_save = list_list[:history_count]
            list_archiving = list_list[history_count:]
    if list_save:
        list_save_yaml = yaml.dump(list_save, Dumper=yaml.RoundTripDumper)
        rest.add_file_to_change(change_no, list_path, list_save_yaml)
    if list_archiving:
        list_archiving_yaml = yaml.dump(list_archiving, Dumper=yaml.RoundTripDumper)
        archiving_path = archiving_path + slugify(arrow.now().isoformat()) + '.yaml'
        rest.add_file_to_change(change_no, archiving_path, list_archiving_yaml)


if __name__ == '__main__':
    main()
