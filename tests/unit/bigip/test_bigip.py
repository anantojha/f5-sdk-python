""" Test BIG-IP module """

# project imports
import base64
import socket
import os
from paramiko import ssh_exception
from f5cloudsdk import exceptions
from f5cloudsdk import constants as project_constants
# unittest imports
from ...global_test_imports import pytest, Mock, call

# local test imports
from ...shared import constants
from ...shared import mock_utils
from . import utils as BigIpUtils

# packages to mock
REQ = constants.MOCK['requests']

DFL_MGMT_PORT = 443

HOST = constants.HOST
USER = constants.USER
USER_PWD = constants.USER_PWD
TOKEN = constants.TOKEN

TOKEN_RESPONSE = {
    'token': {
        'token': TOKEN,
        'selfLink': 'https://localhost/mgmt/shared/authz/tokens/mytoken'
    }
}


class TestBigIp(object):
    """Test Class: bigip module """

    @classmethod
    def setup_class(cls):
        """" Setup func """

        with open(os.path.join(os.path.dirname(__file__), 'sample_rsa_key')) as _f:
            _file = _f.read()

        cls.private_key = base64.b64decode(_file).decode('utf-8')

    @classmethod
    def teardown_class(cls):
        """" Teardown func """

    def setup_method(self):
        """ setup any state tied to the execution of the given method in a
        class
        """
        self.device = BigIpUtils.get_mgmt_client(token=TOKEN)

    def teardown_method(self):
        """ teardown any state that was previously setup with a setup_method
        call
        """

    def test_mgmt_client(self, mocker):
        """Test: Initialize mgmt client

        Assertions
        ----------
        - Device instance token should match 'TOKEN'
        """

        mocker.patch(REQ).return_value.json = Mock(return_value=TOKEN_RESPONSE)

        device = BigIpUtils.get_mgmt_client(user=USER, pwd=USER_PWD)

        assert device.token == TOKEN

    def test_mgmt_client_key_auth(self, mocker):
        """Test: Initialize mgmt client using key-based auth

        Assertions
        ----------
        - Mock ssh client instance exec_command should start with 'tmsh modify'
        - Device instance token should match 'TOKEN'
        """

        mocker.patch(REQ).return_value.json = Mock(return_value=TOKEN_RESPONSE)
        mock_ssh_client_instance = mock_utils.create_ssh_client(
            mocker.patch('paramiko.SSHClient'),
            'auth user %s { description user shell bash }' % (USER)
        )
        mocker.patch('paramiko.rsakey.open', mocker.mock_open(read_data=self.private_key))
        mocker.patch('paramiko.pkey.open', mocker.mock_open(read_data=self.private_key))

        device = BigIpUtils.get_mgmt_client(
            user=USER, pwd=USER_PWD, private_key_file='foo')

        calls = [
            call(' list auth user %s' % (USER)),
            call('tmsh modify auth user %s password %s' % (USER, USER_PWD))
        ]
        mock_ssh_client_instance.exec_command.assert_has_calls(calls)
        assert device.token == TOKEN

    def test_mgmt_client_key_auth_bash(self, mocker):
        """Test: Initialize mgmt client using key-based auth - 'shell bash'

        'list auth user <user>' command response containing 'shell tmsh' means
        command should NOT start with 'tmsh'

        Assertions
        ----------
        - Mock ssh client instance exec_command should start with ' modify'
        - Device instance token should match 'TOKEN'
        """

        mocker.patch(REQ).return_value.json = Mock(return_value=TOKEN_RESPONSE)
        mock_ssh_client_instance = mock_utils.create_ssh_client(
            mocker.patch('paramiko.SSHClient'),
            'auth user %s { description user shell tmsh }' % (USER)
        )
        mocker.patch('paramiko.rsakey.open', mocker.mock_open(read_data=self.private_key))
        mocker.patch('paramiko.pkey.open', mocker.mock_open(read_data=self.private_key))

        device = BigIpUtils.get_mgmt_client(
            user=USER, pwd=USER_PWD, private_key_file='foo')

        calls = [
            call(' list auth user %s' % (USER)),
            call(' modify auth user %s password %s' % (USER, USER_PWD))
        ]
        mock_ssh_client_instance.exec_command.assert_has_calls(calls)
        assert device.token == TOKEN

    def test_port_discovery(self, mocker):
        """Test: Port discovery during mgmt client init

        Assertions
        ----------
        - Mock socket instance 'connect' should be called
        - Device port should match 'DFL_MGMT_PORT'
        - Device port should match 'DFL_MGMT_PORT' when OSError is raised
        """

        mock_socket = mocker.patch('socket.socket').return_value

        device = BigIpUtils.get_mgmt_client(token=TOKEN, port=None)

        mock_socket.connect.assert_called()
        assert device.port == DFL_MGMT_PORT

        # raise OSError (connect refused case) - port should be set to default
        mock_socket = mocker.patch('socket.socket').return_value.connect.side_effect = OSError

        device = BigIpUtils.get_mgmt_client(token=TOKEN, port=None)

        assert device.port == DFL_MGMT_PORT

    def test_port_discovery_timeout(self, mocker):
        """Test: Port discovery during mgmt client init - when timeout occurrs

        Verify result when timeout for all DFL_ ports occurs

        Assertions
        ----------
        - Mock socket instance 'connect' should be called
        - DFL_MGMT_PORT should be returned
        """

        mock_socket = mocker.patch('socket.socket').return_value
        mock_socket.connect.side_effect = socket.timeout

        device = BigIpUtils.get_mgmt_client(token=TOKEN, port=None)

        mock_socket.connect.assert_called()
        assert device.port == DFL_MGMT_PORT

    def test_is_ready(self, mocker):
        """Test: Device ready check

        Assertions
        ----------
        - Mock socket instance 'connect' should be called with correct host/port
        """

        mock_socket = mocker.patch('socket.socket').return_value

        device = BigIpUtils.get_mgmt_client(token=TOKEN, skip_ready_check=False)

        mock_socket.connect.assert_called_with((HOST, device.port))

    def test_is_ready_false(self, mocker):
        """Test: Device ready check should raise exception

        Assertions
        ----------
        - Mgmt client should raise DeviceReadyError on socket.timeout error
        """

        mock_socket = mocker.patch('socket.socket').return_value
        mock_socket.connect.side_effect = socket.timeout

        mocker.patch('time.sleep')

        pytest.raises(
            exceptions.DeviceReadyError,
            BigIpUtils.get_mgmt_client,
            token=TOKEN,
            skip_ready_check=False)

    def test_get_info(self, mocker):
        """Test: get_info

        Assertions
        ----------
        - Device version should match 'version'
        """

        version = '14.1.0.0'
        response = {
            'entries': {
                'https://localhost/mgmt/tm/sys/version/0': {
                    'nestedStats': {
                        'entries': {
                            'Version': {
                                'description': version
                            }
                        }
                    }
                }
            }
        }
        mocker.patch(REQ).return_value.json = Mock(return_value=response)

        device_info = self.device.get_info()
        assert device_info['version'] == version

    def test_make_request_no_token(self, mocker):
        """Test: make_request with no device token

        Assertions
        ----------
        - AuthRequiredError exception should be raised
        """

        mocker.patch(REQ).return_value.json = Mock(return_value={})

        self.device.token = None

        pytest.raises(exceptions.AuthRequiredError, self.device.make_request, '/')

    def test_make_request_auth_header(self, mocker):
        """Test: make_request should insert auth header

        Assertions
        ----------
        - make_request should insert auth header: {'X-F5-Auth-Token': 'token'}
        """

        mock = mocker.patch(REQ)

        self.device.make_request('/')

        _, kwargs = mock.call_args
        assert kwargs['headers'][project_constants.F5_AUTH_TOKEN_HEADER] == TOKEN

    def test_make_request_bool(self, mocker):
        """Test: make_request with bool_response=True

        Assertions
        ----------
        - make_request should return boolean (True)
        """

        mocker.patch(REQ).return_value.json = Mock(return_value={})

        response = self.device.make_request('/', bool_response=True)
        assert response

    def test_make_ssh_request_stderr(self, mocker):
        """Test: make_ssh_request - stderr response should raise exception

        Assertions
        ----------
        - SSHCommandStdError exception should be raised
        """

        mocker.patch(REQ).return_value.json = Mock(return_value=TOKEN_RESPONSE)
        mock_utils.create_ssh_client(
            mocker.patch('paramiko.SSHClient'), '', stderr='error')

        device = BigIpUtils.get_mgmt_client(user=USER, pwd=USER_PWD)

        pytest.raises(exceptions.SSHCommandStdError, device.make_ssh_request, 'command')

    def test_make_ssh_request_connect_error(self, mocker):
        """Test: make_ssh_request - connect exception should raise exception

        Assertions
        ----------
        - SSHException should be raised
        """

        mocker.patch(REQ).return_value.json = Mock(return_value=TOKEN_RESPONSE)
        mock_utils.create_ssh_client(
            mocker.patch('paramiko.SSHClient'), '', connect_raise=ssh_exception.SSHException)

        device = BigIpUtils.get_mgmt_client(user=USER, pwd=USER_PWD)

        pytest.raises(ssh_exception.SSHException, device.make_ssh_request, 'command')
