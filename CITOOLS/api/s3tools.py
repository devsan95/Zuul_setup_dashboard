#! /usr/bin/env python2.7
# -*- coding:utf-8 -*-

"""A collection of functions relating to s3 operations."""

import os
import sys
import traceback
import argparse
import re
import boto3
import api.config
import api.file_api
from tqdm import tqdm


class FolderEmptyException(Exception):
    """
    Exception which raises when encounter an empty directory.
    """
    pass


class S3Server(object):
    """
    A class that represents a s3 server, and contains a collection of function
    to operate it.
    """
    def __init__(self, server):
        """
        Init the object
        Args:
            server(str): server you want to use. Should be section name of
                         s3.properties
        """
        self._conf_reader = api.config.ConfigTool()
        self._conf_reader.load('s3')
        self._server = server
        self._s3_client = None
        self._load_config()

    def _load_config(self):
        """
        Internal function, do not use.
        Load config according to the server, and re-initialize the s3 client.
        Returns:
            None

        """
        self._s3_user = self._conf_reader.get(self._server, 'username')
        self._s3_server = self._conf_reader.get(self._server, 'server')
        self._s3_access_key = self._conf_reader.get(self._server, 'access_key')
        self._s3_secret_key = self._conf_reader.get(self._server, 'secret_key')

        if self._s3_client is not None:
            pass

        self._s3_client = boto3.client(
            service_name='s3',
            aws_access_key_id=self._s3_access_key,
            aws_secret_access_key=self._s3_secret_key,
            endpoint_url='https://' + self._s3_server,
        )
        print('Switched to server config [{}]'.format(self._server))

    @staticmethod
    def parse_s3_url(url):
        """
        Parse s3 url to bucket and key.
        url can be as 's3://bucket/key' or 'http://bucket.domain/key'
        Args:
            url: intput url

        Returns:
            bucket, key
        """
        regex = re.compile(r'[sS]3://([^/]+)/(.*)')
        regex2 = re.compile(r'[^:/]*://([^./]*).[^/]*/(.*)')

        result = regex.match(url)
        if not result:
            result = regex2.match(url)
        if not result:
            raise Exception('Invalid s3 path [{}].'.format(url))
        bucket = result.group(1)
        key = result.group(2)

        return bucket, key

    def _is_folder(self, url, is_local=False):
        """
        Internal function, do not use.
        Judge a url is a directory or not.
        Args:
            url: url to judge
            is_local: if url is a local path or s3 path

        Returns:
            Boolean if the url is a directory or not
        """
        return (is_local or (not self.is_object(url))) and url.endswith('/')

    @staticmethod
    def _progress_hook(tqdm):
        """
        Internal function, do not use.
        A function to generate hook function of s3 and tqdm to display
        upload or download progress.
        Args:
            tqdm: tqdm instance to use

        Returns:
            hook function which boto3 needs
        """
        last_size = [0]

        def inner(size):
            tqdm.update(size - last_size[0])
            last_size[0] = size

        return inner

    def switch_server(self, server):
        """
        Switch to another server.
        Args:
            server(str): server you want to use. Should be section name of
                         s3.properties

        """
        self._server = server
        self._load_config()

    def upload_file(self, file_path, target_path, is_public=False):
        """
        Upload a file to s3.
        Args:
            file_path: local path of the file
            target_path: s3 path of the path
            is_public: whether the s3 path is acl-public-read or not

        Returns:
            None
        """
        if not os.path.exists(file_path):
            raise Exception('Can not find file [{}].'.format(file_path))
        if is_public:
            extra_arg = {'ACL': 'public-read'}
        else:
            extra_arg = {}
        bucket, key = self.parse_s3_url(target_path)
        if self._is_folder(key):
            raise Exception(
                "Target path [{}] should not be a directory".format(
                    target_path))

        with tqdm(total=api.file_api.get_file_size(file_path),
                  miniters=1,
                  unit='B') as pbar:
            pbar.write(
                'Put [{}] as [s3://{}/{}]'.format(file_path, bucket, key))
            self._s3_client.upload_file(file_path, bucket, key,
                                        ExtraArgs=extra_arg,
                                        Callback=self._progress_hook(pbar))

    def upload_directory(self, directory_path, target_path, is_public=False):
        """
        List the content of a directory and upload them one by one.
        Args:
            directory_path: path to the directory
            target_path: path to be uploaded
            is_public: whether the s3 path is acl-public-read or not

        Returns:
            None
        """
        if not os.path.exists(directory_path):
            raise Exception(
                'Path [{}] does not exist.'.format(directory_path))

        if not self._is_folder(directory_path, True):
            raise Exception(
                "Path [{}] is not a directory.".format(directory_path))

        if not self._is_folder(target_path):
            raise Exception(
                "target path [{}] is not a directory".format(target_path))

        file_list = self.list_relative_local_path(directory_path)

        if not file_list:
            raise FolderEmptyException(
                'Folder [{}] is empty!'.format(directory_path))

        with tqdm(file_list) as t:
            t.write('Put files in [{}]'.format(directory_path))
            for file_name in t:
                file_path = file_name.replace('\\', '/')
                self.upload_file(directory_path + file_path,
                                 target_path + file_path,
                                 is_public)

    def is_object(self, path):
        """
        Judge whether a s3 url is an object or not
        Args:
            path: s3 url

        Returns:
            Boolean of the result
        """
        try:
            bucket, key = self.parse_s3_url(path)
        except Exception:
            return False

        try:
            self._s3_client.head_object(Bucket=bucket, Key=key)
        except Exception:
            return False

        return True

    def get_object_size(self, path):
        """
        Get the size of a s3 object
        Args:
            path: path to the s3 object

        Returns:
            size of the object

        """
        bucket, key = self.parse_s3_url(path)
        head_dict = self._s3_client.head_object(Bucket=bucket, Key=key)
        return head_dict['ContentLength']

    def list_relative_remote_path(self, remote_path):
        """
        list all content of a s3 directory
        Args:
            remote_path:  path to the s3 directory

        Returns:
            list of the content in relative path
        """
        bucket, key = self.parse_s3_url(remote_path)

        if not self._is_folder(remote_path):
            raise Exception('Remote path [{}] is not a folder!'.format(
                remote_path))

        object_list = []
        continuation_token = ''
        while True:
            list_result = self._s3_client.list_objects_v2(
                Bucket=bucket, Prefix=key,
                ContinuationToken=continuation_token)
            if 'Contents' not in list_result:
                break
            for obj in list_result['Contents']:
                if obj['Key'].startswith(key):
                    object_list.append(obj['Key'][len(key):])
                else:
                    object_list.append(obj['Key'])
            if list_result['IsTruncated']:
                continuation_token = list_result['NextContinuationToken']
            else:
                break

        return object_list

    def list_relative_local_path(self, local_path):
        """
        list all content in a local directory in relative path
        Args:
            local_path: path to the directory

        Returns:
            list of the contents in relative path
        """
        if not self._is_folder(local_path, True):
            raise Exception('Path [{}] is not a folder!'.format(local_path))

        file_list = api.file_api.list_directory(local_path, True)
        return file_list

    def copy_file(self, src_path, tar_path, is_public=False):
        """
        Copy a file in s3
        Args:
            src_path: source path
            tar_path: destination path
            is_public: whether the destination path is acl-public-read or not

        Returns:
            None
        """
        if not self.is_object(src_path):
            raise Exception(
                'Source [{}] is not a valid object!'.format(src_path))
        if self._is_folder(tar_path):
            raise Exception('Target [{}] is a folder!'.format(tar_path))

        bucket1, key1 = self.parse_s3_url(src_path)
        bucket2, key2 = self.parse_s3_url(tar_path)

        param_dict = {}

        if is_public:
            param_dict['ACL'] = 'public-read'

        param_dict['Bucket'] = bucket2
        param_dict['Key'] = key2
        param_dict['CopySource'] = {
            'Bucket': bucket1,
            'Key': key1
        }

        self._s3_client.copy_object(**param_dict)

    def copy_directory(self, src_path, tar_path, is_public=False):
        """
        List the content of a directory and copy them one by one.
        Args:
            src_path: source path
            tar_path: destination path
            is_public: whether the destination path is acl-public-read or not

        Returns:
            None
        """
        if not self._is_folder(src_path):
            raise Exception('Source [{}] is not a folder!'.format(src_path))
        if not self._is_folder(tar_path):
            raise Exception('Target [{}] is not a folder!'.format(tar_path))
        file_list = self.list_relative_remote_path(src_path)
        if not file_list:
            raise FolderEmptyException(
                'Folder [{}] is empty!'.format(src_path))

        with tqdm(file_list) as t:
            t.write('Copy folder [{}] to [{}]'.format(src_path, tar_path))
            for file_name in t:
                t.write('Copy file [{}] to [{}]'.format(
                    src_path + file_name, tar_path + file_name))
                self.copy_file(src_path + file_name,
                               tar_path + file_name,
                               is_public)

    def download_file(self, s3_path, local_path):
        """
        Download file from s3 to local.
        Args:
            s3_path: path to s3 object
            local_path: path to save the object

        Returns:
            None
        """
        if not self.is_object(s3_path):
            raise Exception('Path [{}] is not an object!'.format(s3_path))
        if self._is_folder(local_path, True):
            raise Exception('Path [{}] is a folder!'.format(local_path))

        api.file_api.make_dirs_for_file(local_path)

        bucket, key = self.parse_s3_url(s3_path)
        with tqdm(total=self.get_object_size(s3_path),
                  miniters=1,
                  unit='B') as pbar:
            pbar.write(
                'Get [s3://{}/{}] as [{}]'.format(bucket, key, local_path))
            self._s3_client.download_file(bucket, key, local_path,
                                          Callback=self._progress_hook(pbar))

    def download_directory(self, s3_path, local_path):
        """
        list all content of a s3 path and download them one by one.
        Args:
            s3_path: path to s3 directory
            local_path: path to save the contents

        Returns:
            None
        """
        if not self._is_folder(s3_path):
            raise Exception('S3 path [{}] is not a folder'.format(s3_path))
        if not self._is_folder(local_path, True):
            raise Exception(
                'Local path [{}] is not a folder'.format(local_path))
        file_list = self.list_relative_remote_path(s3_path)
        with tqdm(file_list) as t:
            t.write('Get Folder [{}] to [{}]'.format(
                s3_path, local_path
            ))
            for file_name in t:
                self.download_file(s3_path + file_name,
                                   os.path.join(local_path, file_name))

    def delete_file(self, target_path):
        """
        Delete a s3 object
        Args:
            target_path: path to the object

        Returns:
            None
        """
        if not self.is_object(target_path):
            raise Exception(
                'Target [{}] is not an object!'.format(target_path))

        bucket, key = self.parse_s3_url(target_path)
        self._s3_client.delete_object(Bucket=bucket, Key=key)

    def delete_directory(self, target_directory):
        """
        List all contents of a directory and delete them one by one
        Args:
            target_directory: path to s3 directory to delete

        Returns:
            None
        """
        list = self.list_relative_remote_path(target_directory)
        if not list:
            raise FolderEmptyException(
                'Folder [{}] is empty!'.format(target_directory))
        with tqdm(list) as t:
            t.write('Delete lists from [{}]'.format(target_directory))
            for file in t:
                t.write('Delete [{}]'.format(target_directory + file))
                self.delete_file(target_directory + file)

    def upload(self, file_path, target_path, is_public=False):
        """
        upload to s3, judge if the path is directory and invoke corresponding
        functions.
        Args:
            file_path: path to be uploaded
            target_path: path of destination
            is_public: if the destination is acl-public-read or note

        Returns:
            None
        """
        if self._is_folder(file_path, True):
            if self._is_folder(target_path):
                self.upload_directory(file_path, target_path, is_public)
            else:
                raise Exception(
                    '[{}] is folder but [{}] is not!'.format(
                        file_path, target_path))
        else:
            if self._is_folder(target_path):
                file_name = os.path.basename(file_path)
                self.upload_file(file_path, target_path + file_name, is_public)
            else:
                self.upload_file(file_path, target_path, is_public)
        pass

    def copy(self, src_path, target_path, is_public=False):
        """
        copy in s3, judge if the path is directory and invoke corresponding
        functions.
        Args:
            src_path: path of source
            target_path: path of destination
            is_public: if the destination is acl-public-read or note

        Returns:
            None
        """
        if self._is_folder(src_path):
            if self._is_folder(target_path):
                self.copy_directory(src_path, target_path, is_public)
            else:
                raise Exception(
                    '[{}] is folder but [{}] is not!'.format(
                        src_path, target_path))
        else:
            if self._is_folder(target_path):
                file_name = src_path.split('/')[-1]
                self.copy_file(src_path, target_path + file_name, is_public)
            else:
                self.copy_file(src_path, target_path, is_public)
        pass

    def download(self, src_path, local_path):
        """
        download from s3, judge if the path is directory and invoke
        corresponding functions.
        Args:
            src_path: path of source
            local_path: path of destination

        Returns:
            None
        """
        if self._is_folder(src_path):
            if self._is_folder(local_path, True):
                self.download_directory(src_path, local_path)
            else:
                raise Exception(
                    '[{}] is folder but [{}] is not!'.format(
                        src_path, local_path))
        else:
            if self._is_folder(local_path, True):
                file_name = src_path.split('/')[-1]
                self.download_file(src_path,
                                   os.path.join(local_path, file_name))
            else:
                self.download_file(src_path, local_path)
        pass

    def delete(self, target_path):
        """
        delete from s3, judge if the path is directory and invoke corresponding
        functions.
        Args:
            target_path: path to delete

        Returns:
            None
        """
        if self._is_folder(target_path):
            self.delete_directory(target_path)
        else:
            self.delete_file(target_path)

    def list(self, target_path):
        """
        Print all contents of a path.
        if the path is 's3://' then print all buckets
        Args:
            target_path: path to list

        Returns:
            None
        """
        if target_path == 's3://':
            for line in self.list_bucket():
                print('s3://{}'.format(line))
        else:
            for line in self.list_directory(target_path):
                print(line)

    def list_bucket(self):
        """
        list all buckets.
        Returns:
            list of buckets.
        """
        response = self._s3_client.list_buckets()
        buckets = []
        if 'Buckets' in response:
            for item in response['Buckets']:
                buckets.append(item['Name'])
        return buckets

    def list_directory(self, path):
        """
        list all contents in a s3 directory in absolute path
        Args:
            path: path to list

        Returns:
            list of all contents in absolute path
        """
        bucket, key = self.parse_s3_url(path)

        if not self._is_folder(path):
            raise Exception('Remote path [{}] is not a folder!'.format(path))

        object_list = []
        continuation_token = ''
        while True:
            list_result = self._s3_client.list_objects_v2(
                Bucket=bucket, Prefix=key,
                ContinuationToken=continuation_token)
            if 'Contents' not in list_result:
                break
            for obj in list_result['Contents']:
                object_list.append('s3://{}/{}'.format(bucket, obj['Key']))
            if list_result['IsTruncated']:
                continuation_token = list_result['NextContinuationToken']
            else:
                break

        return object_list


def _main(**kwargs):
    s3 = S3Server(kwargs['server'])
    op = kwargs['operation']
    if op == 'get':
        s3.download(kwargs['source'], kwargs['destination'])
    elif op == 'put':
        s3.upload(kwargs['source'], kwargs['destination'])
    elif op == 'copy':
        s3.copy(kwargs['source'], kwargs['destination'])
    elif op == 'del':
        s3.delete(kwargs['source'])
    elif op == 'ls':
        s3.list(kwargs['source'])
    else:
        raise Exception('Operation [{}] not supported.'.format(op))


def _parse_args():
    parser = argparse.ArgumentParser(description='Operate S3 server.')

    subparsers = parser.add_subparsers(title='Operation',
                                       description='Operations to perform',
                                       dest='operation')
    parser_put = subparsers.add_parser('put',
                                       help='put file or folder to s3')
    parser_get = subparsers.add_parser('get',
                                       help='get file or folder from s3')
    parser_copy = subparsers.add_parser('copy',
                                        help='copy file or folder in s3')
    parser_delete = subparsers.add_parser('del',
                                          help='delete file or folder in s3')
    parser_list = subparsers.add_parser('ls',
                                        help='list s3 file tree')

    parser.add_argument('--server', '-s', nargs='?',
                        type=str, dest='server', required=True,
                        help='which server to operate, '
                             'server is configured in properties file')

    _add_arguments_to_subparser(parser_get)
    _add_arguments_to_subparser(parser_put)
    _add_arguments_to_subparser(parser_copy)
    _add_argument_to_subparser(parser_delete)
    _add_argument_to_subparser(parser_list)

    args = parser.parse_args()
    return vars(args)


def _add_arguments_to_subparser(parser):
    parser.add_argument('source', type=str,
                        help='source path to operate')
    parser.add_argument('destination', type=str,
                        help='destination path to operate')


def _add_argument_to_subparser(parser):
    parser.add_argument('source', type=str,
                        help='source path to operate')


if __name__ == '__main__':
    try:
        traceback.print_exc()
        param = _parse_args()

        _main(**param)
    except Exception as e:
        print("An exception %s occurred, msg: %s" % (type(e), str(e)))
        traceback.print_exc()
        sys.exit(2)
