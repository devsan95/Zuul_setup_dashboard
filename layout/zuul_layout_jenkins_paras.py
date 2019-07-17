def main_params(item, params):
    params['ZUULEX_COMMIT_MESSAGE'] = item.change._data['commitMessage']
    params['ZUULEX_CHANGE_STATUS'] = item.change._data['status']
    params['ZUULEX_CHANGE_URL'] = item.change._data['url']
    params['ZUULEX_CHANGE_ID'] = item.change._data['id']
    params['ZUULEX_CHANGE_REVISION'] = item.change._data['currentPatchSet']['revision']
    params['ZUULEX_CHANGE_SIZE_INSERTIONS'] = item.change._data['currentPatchSet']['sizeInsertions']
    params['ZUULEX_CHANGE_SIZE_DELETIONS'] = item.change._data['currentPatchSet']['sizeDeletions']
#    params['CHANGE_PARENT_REV'] = item.change._data['currentPatchSet']['parents']

    params['ZUULEX_CHANGE_PARENT_ISCURRENTPATCHSET'] = item.change._data['dependsOn']['isCurrentPatchSet']
    params['ZUULEX_CHANGE_PARENT_REVISION'] = item.change._data['dependsOn']['revision']
    params['ZUULEX_CHANGE_PARENT_REF'] = item.change._data['dependsOn']['ref']
    params['ZUULEX_CHANGE_PARENT_ID'] = item.change._data['dependsOn']['id']
    params['ZUULEX_CHANGE_PARENT_NO'] = item.change._data['dependsOn']['number']

    params['ZUULEX_CHANGE_OWNER_USERNAME'] = item.change._data['owner']['username']
    params['ZUULEX_CHANGE_OWNER_NAME'] = item.change._data['owner']['name']
    params['ZUULEX_CHANGE_OWNER_EMAIL'] = item.change._data['owner']['email']

    params['ZUULEX_CHANGE_UPLOADER_USERNAME'] = item.change._data['currentPatchSet']['uploader']['username']
    params['ZUULEX_CHANGE_UPLOADER_NAME'] = item.change._data['currentPatchSet']['uploader']['name']
    params['ZUULEX_CHANGE_UPLOADER_EMAIL'] = item.change._data['currentPatchSet']['uploader']['email']

    params['ZUULEX_CHANGE_AUTHOR_USERNAME'] = item.change._data['currentPatchSet']['author']['username']
    params['ZUULEX_CHANGE_AUTHOR_NAME'] = item.change._data['currentPatchSet']['author']['name']
    params['ZUULEX_CHANGE_AUTHOR_EMAIL'] = item.change._data['currentPatchSet']['author']['email']


def temp_params(item, params):
    main_params(item, params)
#    params['ROOT_PATH'] = '/aaa/bbb/ccc'
