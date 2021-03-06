# Copyright (c) 2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"Tests for swift.common.swob"

import datetime
import unittest
import re
import time
from StringIO import StringIO
from urllib import quote

import swift.common.swob
from swift.common import utils, exceptions


class TestHeaderEnvironProxy(unittest.TestCase):
    def test_proxy(self):
        environ = {}
        proxy = swift.common.swob.HeaderEnvironProxy(environ)
        proxy['Content-Length'] = 20
        proxy['Content-Type'] = 'text/plain'
        proxy['Something-Else'] = 'somevalue'
        self.assertEquals(
            proxy.environ, {'CONTENT_LENGTH': '20',
                            'CONTENT_TYPE': 'text/plain',
                            'HTTP_SOMETHING_ELSE': 'somevalue'})
        self.assertEquals(proxy['content-length'], '20')
        self.assertEquals(proxy['content-type'], 'text/plain')
        self.assertEquals(proxy['something-else'], 'somevalue')

    def test_del(self):
        environ = {}
        proxy = swift.common.swob.HeaderEnvironProxy(environ)
        proxy['Content-Length'] = 20
        proxy['Content-Type'] = 'text/plain'
        proxy['Something-Else'] = 'somevalue'
        del proxy['Content-Length']
        del proxy['Content-Type']
        del proxy['Something-Else']
        self.assertEquals(proxy.environ, {})

    def test_contains(self):
        environ = {}
        proxy = swift.common.swob.HeaderEnvironProxy(environ)
        proxy['Content-Length'] = 20
        proxy['Content-Type'] = 'text/plain'
        proxy['Something-Else'] = 'somevalue'
        self.assert_('content-length' in proxy)
        self.assert_('content-type' in proxy)
        self.assert_('something-else' in proxy)

    def test_keys(self):
        environ = {}
        proxy = swift.common.swob.HeaderEnvironProxy(environ)
        proxy['Content-Length'] = 20
        proxy['Content-Type'] = 'text/plain'
        proxy['Something-Else'] = 'somevalue'
        self.assertEquals(
            set(proxy.keys()),
            set(('Content-Length', 'Content-Type', 'Something-Else')))


class TestHeaderKeyDict(unittest.TestCase):
    def test_case_insensitive(self):
        headers = swift.common.swob.HeaderKeyDict()
        headers['Content-Length'] = 0
        headers['CONTENT-LENGTH'] = 10
        headers['content-length'] = 20
        self.assertEquals(headers['Content-Length'], '20')
        self.assertEquals(headers['content-length'], '20')
        self.assertEquals(headers['CONTENT-LENGTH'], '20')

    def test_setdefault(self):
        headers = swift.common.swob.HeaderKeyDict()

        # it gets set
        headers.setdefault('x-rubber-ducky', 'the one')
        self.assertEquals(headers['X-Rubber-Ducky'], 'the one')

        # it has the right return value
        ret = headers.setdefault('x-boat', 'dinghy')
        self.assertEquals(ret, 'dinghy')

        ret = headers.setdefault('x-boat', 'yacht')
        self.assertEquals(ret, 'dinghy')

        # shouldn't crash
        headers.setdefault('x-sir-not-appearing-in-this-request', None)

    def test_del_contains(self):
        headers = swift.common.swob.HeaderKeyDict()
        headers['Content-Length'] = 0
        self.assert_('Content-Length' in headers)
        del headers['Content-Length']
        self.assert_('Content-Length' not in headers)

    def test_update(self):
        headers = swift.common.swob.HeaderKeyDict()
        headers.update({'Content-Length': '0'})
        headers.update([('Content-Type', 'text/plain')])
        self.assertEquals(headers['Content-Length'], '0')
        self.assertEquals(headers['Content-Type'], 'text/plain')

    def test_get(self):
        headers = swift.common.swob.HeaderKeyDict()
        headers['content-length'] = 20
        self.assertEquals(headers.get('CONTENT-LENGTH'), '20')
        self.assertEquals(headers.get('something-else'), None)
        self.assertEquals(headers.get('something-else', True), True)

    def test_keys(self):
        headers = swift.common.swob.HeaderKeyDict()
        headers['content-length'] = 20
        headers['cOnTent-tYpe'] = 'text/plain'
        headers['SomeThing-eLse'] = 'somevalue'
        self.assertEquals(
            set(headers.keys()),
            set(('Content-Length', 'Content-Type', 'Something-Else')))


class TestRange(unittest.TestCase):
    def test_range(self):
        range = swift.common.swob.Range('bytes=1-7')
        self.assertEquals(range.ranges[0], (1, 7))

    def test_upsidedown_range(self):
        range = swift.common.swob.Range('bytes=5-10')
        self.assertEquals(range.ranges_for_length(2), [])

    def test_str(self):
        for range_str in ('bytes=1-7', 'bytes=1-', 'bytes=-1',
                          'bytes=1-7,9-12', 'bytes=-7,9-'):
            range = swift.common.swob.Range(range_str)
            self.assertEquals(str(range), range_str)

    def test_ranges_for_length(self):
        range = swift.common.swob.Range('bytes=1-7')
        self.assertEquals(range.ranges_for_length(10), [(1, 8)])
        self.assertEquals(range.ranges_for_length(5), [(1, 5)])
        self.assertEquals(range.ranges_for_length(None), None)

    def test_ranges_for_large_length(self):
        range = swift.common.swob.Range('bytes=-1000000000000000000000000000')
        self.assertEquals(range.ranges_for_length(100), [(0, 100)])

    def test_ranges_for_length_no_end(self):
        range = swift.common.swob.Range('bytes=1-')
        self.assertEquals(range.ranges_for_length(10), [(1, 10)])
        self.assertEquals(range.ranges_for_length(5), [(1, 5)])
        self.assertEquals(range.ranges_for_length(None), None)
        # This used to freak out:
        range = swift.common.swob.Range('bytes=100-')
        self.assertEquals(range.ranges_for_length(5), [])
        self.assertEquals(range.ranges_for_length(None), None)

        range = swift.common.swob.Range('bytes=4-6,100-')
        self.assertEquals(range.ranges_for_length(5), [(4, 5)])

    def test_ranges_for_length_no_start(self):
        range = swift.common.swob.Range('bytes=-7')
        self.assertEquals(range.ranges_for_length(10), [(3, 10)])
        self.assertEquals(range.ranges_for_length(5), [(0, 5)])
        self.assertEquals(range.ranges_for_length(None), None)

        range = swift.common.swob.Range('bytes=4-6,-100')
        self.assertEquals(range.ranges_for_length(5), [(4, 5), (0, 5)])

    def test_ranges_for_length_multi(self):
        range = swift.common.swob.Range('bytes=-20,4-,30-150,-10')
        # the length of the ranges should be 4
        self.assertEquals(len(range.ranges_for_length(200)), 4)

        # the actual length less than any of the range
        self.assertEquals(range.ranges_for_length(90),
                          [(70, 90), (4, 90), (30, 90), (80, 90)])

        # the actual length greater than any of the range
        self.assertEquals(range.ranges_for_length(200),
                          [(180, 200), (4, 200), (30, 151), (190, 200)])

        self.assertEquals(range.ranges_for_length(None), None)

    def test_ranges_for_length_edges(self):
        range = swift.common.swob.Range('bytes=0-1, -7')
        self.assertEquals(range.ranges_for_length(10),
                          [(0, 2), (3, 10)])

        range = swift.common.swob.Range('bytes=-7, 0-1')
        self.assertEquals(range.ranges_for_length(10),
                          [(3, 10), (0, 2)])

        range = swift.common.swob.Range('bytes=-7, 0-1')
        self.assertEquals(range.ranges_for_length(5),
                          [(0, 5), (0, 2)])

    def test_range_invalid_syntax(self):

        def _check_invalid_range(range_value):
            try:
                swift.common.swob.Range(range_value)
                return False
            except ValueError:
                return True

        """
        All the following cases should result ValueError exception
        1. value not starts with bytes=
        2. range value start is greater than the end, eg. bytes=5-3
        3. range does not have start or end, eg. bytes=-
        4. range does not have hyphen, eg. bytes=45
        5. range value is non numeric
        6. any combination of the above
        """

        self.assert_(_check_invalid_range('nonbytes=foobar,10-2'))
        self.assert_(_check_invalid_range('bytes=5-3'))
        self.assert_(_check_invalid_range('bytes=-'))
        self.assert_(_check_invalid_range('bytes=45'))
        self.assert_(_check_invalid_range('bytes=foo-bar,3-5'))
        self.assert_(_check_invalid_range('bytes=4-10,45'))
        self.assert_(_check_invalid_range('bytes=foobar,3-5'))
        self.assert_(_check_invalid_range('bytes=nonumber-5'))
        self.assert_(_check_invalid_range('bytes=nonumber'))


class TestMatch(unittest.TestCase):
    def test_match(self):
        match = swift.common.swob.Match('"a", "b"')
        self.assertEquals(match.tags, set(('a', 'b')))
        self.assert_('a' in match)
        self.assert_('b' in match)
        self.assert_('c' not in match)

    def test_match_star(self):
        match = swift.common.swob.Match('"a", "*"')
        self.assert_('a' in match)
        self.assert_('b' in match)
        self.assert_('c' in match)

    def test_match_noquote(self):
        match = swift.common.swob.Match('a, b')
        self.assertEquals(match.tags, set(('a', 'b')))
        self.assert_('a' in match)
        self.assert_('b' in match)
        self.assert_('c' not in match)


class TestAccept(unittest.TestCase):
    def test_accept_json(self):
        for accept in ('application/json', 'application/json;q=1.0,*/*;q=0.9',
                       '*/*;q=0.9,application/json;q=1.0', 'application/*',
                       'text/*,application/json', 'application/*,text/*',
                       'application/json,text/xml'):
            acc = swift.common.swob.Accept(accept)
            match = acc.best_match(['text/plain', 'application/json',
                                    'application/xml', 'text/xml'])
            self.assertEquals(match, 'application/json')

    def test_accept_plain(self):
        for accept in ('', 'text/plain', 'application/xml;q=0.8,*/*;q=0.9',
                       '*/*;q=0.9,application/xml;q=0.8', '*/*',
                       'text/plain,application/xml'):
            acc = swift.common.swob.Accept(accept)
            match = acc.best_match(['text/plain', 'application/json',
                                    'application/xml', 'text/xml'])
            self.assertEquals(match, 'text/plain')

    def test_accept_xml(self):
        for accept in ('application/xml', 'application/xml;q=1.0,*/*;q=0.9',
                       '*/*;q=0.9,application/xml;q=1.0',
                       'application/xml;charset=UTF-8',
                       'application/xml;charset=UTF-8;qws="quoted with space"',
                       'application/xml; q=0.99 ; qws="quoted with space"'):
            acc = swift.common.swob.Accept(accept)
            match = acc.best_match(['text/plain', 'application/xml',
                                   'text/xml'])
            self.assertEquals(match, 'application/xml')

    def test_accept_invalid(self):
        for accept in ('*', 'text/plain,,', 'some stuff',
                       'application/xml;q=1.0;q=1.1', 'text/plain,*',
                       'text /plain', 'text\x7f/plain',
                       'text/plain;a=b=c',
                       'text/plain;q=1;q=2',
                       'text/plain; ubq="unbalanced " quotes"'):
            acc = swift.common.swob.Accept(accept)
            match = acc.best_match(['text/plain', 'application/xml',
                                   'text/xml'])
            self.assertEquals(match, None)

    def test_repr(self):
        acc = swift.common.swob.Accept("application/json")
        self.assertEquals(repr(acc), "application/json")


class TestRequest(unittest.TestCase):
    def test_blank(self):
        req = swift.common.swob.Request.blank(
            '/', environ={'REQUEST_METHOD': 'POST'},
            headers={'Content-Type': 'text/plain'}, body='hi')
        self.assertEquals(req.path_info, '/')
        self.assertEquals(req.body, 'hi')
        self.assertEquals(req.headers['Content-Type'], 'text/plain')
        self.assertEquals(req.method, 'POST')

    def test_blank_req_environ_property_args(self):
        blank = swift.common.swob.Request.blank
        req = blank('/', method='PATCH')
        self.assertEquals(req.method, 'PATCH')
        self.assertEquals(req.environ['REQUEST_METHOD'], 'PATCH')
        req = blank('/', referer='http://example.com')
        self.assertEquals(req.referer, 'http://example.com')
        self.assertEquals(req.referrer, 'http://example.com')
        self.assertEquals(req.environ['HTTP_REFERER'], 'http://example.com')
        self.assertEquals(req.headers['Referer'], 'http://example.com')
        req = blank('/', script_name='/application')
        self.assertEquals(req.script_name, '/application')
        self.assertEquals(req.environ['SCRIPT_NAME'], '/application')
        req = blank('/', host='www.example.com')
        self.assertEquals(req.host, 'www.example.com')
        self.assertEquals(req.environ['HTTP_HOST'], 'www.example.com')
        self.assertEquals(req.headers['Host'], 'www.example.com')
        req = blank('/', remote_addr='127.0.0.1')
        self.assertEquals(req.remote_addr, '127.0.0.1')
        self.assertEquals(req.environ['REMOTE_ADDR'], '127.0.0.1')
        req = blank('/', remote_user='username')
        self.assertEquals(req.remote_user, 'username')
        self.assertEquals(req.environ['REMOTE_USER'], 'username')
        req = blank('/', user_agent='curl/7.22.0 (x86_64-pc-linux-gnu)')
        self.assertEquals(req.user_agent, 'curl/7.22.0 (x86_64-pc-linux-gnu)')
        self.assertEquals(req.environ['HTTP_USER_AGENT'],
                          'curl/7.22.0 (x86_64-pc-linux-gnu)')
        self.assertEquals(req.headers['User-Agent'],
                          'curl/7.22.0 (x86_64-pc-linux-gnu)')
        req = blank('/', query_string='a=b&c=d')
        self.assertEquals(req.query_string, 'a=b&c=d')
        self.assertEquals(req.environ['QUERY_STRING'], 'a=b&c=d')
        req = blank('/', if_match='*')
        self.assertEquals(req.environ['HTTP_IF_MATCH'], '*')
        self.assertEquals(req.headers['If-Match'], '*')

        # multiple environ property kwargs
        req = blank('/', method='PATCH', referer='http://example.com',
                    script_name='/application', host='www.example.com',
                    remote_addr='127.0.0.1', remote_user='username',
                    user_agent='curl/7.22.0 (x86_64-pc-linux-gnu)',
                    query_string='a=b&c=d', if_match='*')
        self.assertEquals(req.method, 'PATCH')
        self.assertEquals(req.referer, 'http://example.com')
        self.assertEquals(req.script_name, '/application')
        self.assertEquals(req.host, 'www.example.com')
        self.assertEquals(req.remote_addr, '127.0.0.1')
        self.assertEquals(req.remote_user, 'username')
        self.assertEquals(req.user_agent, 'curl/7.22.0 (x86_64-pc-linux-gnu)')
        self.assertEquals(req.query_string, 'a=b&c=d')
        self.assertEquals(req.environ['QUERY_STRING'], 'a=b&c=d')

    def test_invalid_req_environ_property_args(self):
        # getter only property
        try:
            swift.common.swob.Request.blank('/', params={'a': 'b'})
        except TypeError as e:
            self.assertEquals("got unexpected keyword argument 'params'",
                              str(e))
        else:
            self.assert_(False, "invalid req_environ_property "
                         "didn't raise error!")
        # regular attribute
        try:
            swift.common.swob.Request.blank('/', _params_cache={'a': 'b'})
        except TypeError as e:
            self.assertEquals("got unexpected keyword "
                              "argument '_params_cache'", str(e))
        else:
            self.assert_(False, "invalid req_environ_property "
                         "didn't raise error!")
        # non-existent attribute
        try:
            swift.common.swob.Request.blank('/', params_cache={'a': 'b'})
        except TypeError as e:
            self.assertEquals("got unexpected keyword "
                              "argument 'params_cache'", str(e))
        else:
            self.assert_(False, "invalid req_environ_property "
                         "didn't raise error!")
        # method
        try:
            swift.common.swob.Request.blank(
                '/', as_referer='GET http://example.com')
        except TypeError as e:
            self.assertEquals("got unexpected keyword "
                              "argument 'as_referer'", str(e))
        else:
            self.assert_(False, "invalid req_environ_property "
                         "didn't raise error!")

    def test_blank_path_info_precedence(self):
        blank = swift.common.swob.Request.blank
        req = blank('/a')
        self.assertEquals(req.path_info, '/a')
        req = blank('/a', environ={'PATH_INFO': '/a/c'})
        self.assertEquals(req.path_info, '/a/c')
        req = blank('/a', environ={'PATH_INFO': '/a/c'}, path_info='/a/c/o')
        self.assertEquals(req.path_info, '/a/c/o')
        req = blank('/a', path_info='/a/c/o')
        self.assertEquals(req.path_info, '/a/c/o')

    def test_blank_body_precedence(self):
        req = swift.common.swob.Request.blank(
            '/', environ={'REQUEST_METHOD': 'POST',
                          'wsgi.input': StringIO('')},
            headers={'Content-Type': 'text/plain'}, body='hi')
        self.assertEquals(req.path_info, '/')
        self.assertEquals(req.body, 'hi')
        self.assertEquals(req.headers['Content-Type'], 'text/plain')
        self.assertEquals(req.method, 'POST')
        body_file = StringIO('asdf')
        req = swift.common.swob.Request.blank(
            '/', environ={'REQUEST_METHOD': 'POST',
                          'wsgi.input': StringIO('')},
            headers={'Content-Type': 'text/plain'}, body='hi',
            body_file=body_file)
        self.assert_(req.body_file is body_file)
        req = swift.common.swob.Request.blank(
            '/', environ={'REQUEST_METHOD': 'POST',
                          'wsgi.input': StringIO('')},
            headers={'Content-Type': 'text/plain'}, body='hi',
            content_length=3)
        self.assertEquals(req.content_length, 3)
        self.assertEquals(len(req.body), 2)

    def test_blank_parsing(self):
        req = swift.common.swob.Request.blank('http://test.com/')
        self.assertEquals(req.environ['wsgi.url_scheme'], 'http')
        self.assertEquals(req.environ['SERVER_PORT'], '80')
        self.assertEquals(req.environ['SERVER_NAME'], 'test.com')

        req = swift.common.swob.Request.blank('https://test.com:456/')
        self.assertEquals(req.environ['wsgi.url_scheme'], 'https')
        self.assertEquals(req.environ['SERVER_PORT'], '456')

        req = swift.common.swob.Request.blank('test.com/')
        self.assertEquals(req.environ['wsgi.url_scheme'], 'http')
        self.assertEquals(req.environ['SERVER_PORT'], '80')
        self.assertEquals(req.environ['PATH_INFO'], 'test.com/')

        self.assertRaises(TypeError, swift.common.swob.Request.blank,
                          'ftp://test.com/')

    def test_params(self):
        req = swift.common.swob.Request.blank('/?a=b&c=d')
        self.assertEquals(req.params['a'], 'b')
        self.assertEquals(req.params['c'], 'd')

    def test_timestamp_missing(self):
        req = swift.common.swob.Request.blank('/')
        self.assertRaises(exceptions.InvalidTimestamp,
                          getattr, req, 'timestamp')

    def test_timestamp_invalid(self):
        req = swift.common.swob.Request.blank(
            '/', headers={'X-Timestamp': 'asdf'})
        self.assertRaises(exceptions.InvalidTimestamp,
                          getattr, req, 'timestamp')

    def test_timestamp(self):
        req = swift.common.swob.Request.blank(
            '/', headers={'X-Timestamp': '1402447134.13507_00000001'})
        expected = utils.Timestamp('1402447134.13507', offset=1)
        self.assertEqual(req.timestamp, expected)
        self.assertEqual(req.timestamp.normal, expected.normal)
        self.assertEqual(req.timestamp.internal, expected.internal)

    def test_path(self):
        req = swift.common.swob.Request.blank('/hi?a=b&c=d')
        self.assertEquals(req.path, '/hi')
        req = swift.common.swob.Request.blank(
            '/', environ={'SCRIPT_NAME': '/hi', 'PATH_INFO': '/there'})
        self.assertEquals(req.path, '/hi/there')

    def test_path_question_mark(self):
        req = swift.common.swob.Request.blank('/test%3Ffile')
        # This tests that .blank unquotes the path when setting PATH_INFO
        self.assertEquals(req.environ['PATH_INFO'], '/test?file')
        # This tests that .path requotes it
        self.assertEquals(req.path, '/test%3Ffile')

    def test_path_info_pop(self):
        req = swift.common.swob.Request.blank('/hi/there')
        self.assertEquals(req.path_info_pop(), 'hi')
        self.assertEquals(req.path_info, '/there')
        self.assertEquals(req.script_name, '/hi')

    def test_bad_path_info_pop(self):
        req = swift.common.swob.Request.blank('blahblah')
        self.assertEquals(req.path_info_pop(), None)

    def test_path_info_pop_last(self):
        req = swift.common.swob.Request.blank('/last')
        self.assertEquals(req.path_info_pop(), 'last')
        self.assertEquals(req.path_info, '')
        self.assertEquals(req.script_name, '/last')

    def test_path_info_pop_none(self):
        req = swift.common.swob.Request.blank('/')
        self.assertEquals(req.path_info_pop(), '')
        self.assertEquals(req.path_info, '')
        self.assertEquals(req.script_name, '/')

    def test_copy_get(self):
        req = swift.common.swob.Request.blank(
            '/hi/there', environ={'REQUEST_METHOD': 'POST'})
        self.assertEquals(req.method, 'POST')
        req2 = req.copy_get()
        self.assertEquals(req2.method, 'GET')

    def test_get_response(self):
        def test_app(environ, start_response):
            start_response('200 OK', [])
            return ['hi']

        req = swift.common.swob.Request.blank('/')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(resp.body, 'hi')

    def test_401_unauthorized(self):
        # No request environment
        resp = swift.common.swob.HTTPUnauthorized()
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        # Request environment
        req = swift.common.swob.Request.blank('/')
        resp = swift.common.swob.HTTPUnauthorized(request=req)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)

    def test_401_valid_account_path(self):

        def test_app(environ, start_response):
            start_response('401 Unauthorized', [])
            return ['hi']

        # Request environment contains valid account in path
        req = swift.common.swob.Request.blank('/v1/account-name')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="account-name"',
                          resp.headers['Www-Authenticate'])

        # Request environment contains valid account/container in path
        req = swift.common.swob.Request.blank('/v1/account-name/c')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="account-name"',
                          resp.headers['Www-Authenticate'])

    def test_401_invalid_path(self):

        def test_app(environ, start_response):
            start_response('401 Unauthorized', [])
            return ['hi']

        # Request environment contains bad path
        req = swift.common.swob.Request.blank('/random')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="unknown"',
                          resp.headers['Www-Authenticate'])

    def test_401_non_keystone_auth_path(self):

        def test_app(environ, start_response):
            start_response('401 Unauthorized', [])
            return ['no creds in request']

        # Request to get token
        req = swift.common.swob.Request.blank('/v1.0/auth')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="unknown"',
                          resp.headers['Www-Authenticate'])

        # Other form of path
        req = swift.common.swob.Request.blank('/auth/v1.0')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="unknown"',
                          resp.headers['Www-Authenticate'])

    def test_401_www_authenticate_exists(self):

        def test_app(environ, start_response):
            start_response('401 Unauthorized', {
                           'Www-Authenticate': 'Me realm="whatever"'})
            return ['no creds in request']

        # Auth middleware sets own Www-Authenticate
        req = swift.common.swob.Request.blank('/auth/v1.0')
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Me realm="whatever"',
                          resp.headers['Www-Authenticate'])

    def test_401_www_authenticate_is_quoted(self):

        def test_app(environ, start_response):
            start_response('401 Unauthorized', [])
            return ['hi']

        hacker = 'account-name\n\n<b>foo<br>'  # url injection test
        quoted_hacker = quote(hacker)
        req = swift.common.swob.Request.blank('/v1/' + hacker)
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="%s"' % quoted_hacker,
                          resp.headers['Www-Authenticate'])

        req = swift.common.swob.Request.blank('/v1/' + quoted_hacker)
        resp = req.get_response(test_app)
        self.assertEquals(resp.status_int, 401)
        self.assert_('Www-Authenticate' in resp.headers)
        self.assertEquals('Swift realm="%s"' % quoted_hacker,
                          resp.headers['Www-Authenticate'])

    def test_not_401(self):

        # Other status codes should not have WWW-Authenticate in response
        def test_app(environ, start_response):
            start_response('200 OK', [])
            return ['hi']

        req = swift.common.swob.Request.blank('/')
        resp = req.get_response(test_app)
        self.assert_('Www-Authenticate' not in resp.headers)

    def test_properties(self):
        req = swift.common.swob.Request.blank('/hi/there', body='hi')

        self.assertEquals(req.body, 'hi')
        self.assertEquals(req.content_length, 2)

        req.remote_addr = 'something'
        self.assertEquals(req.environ['REMOTE_ADDR'], 'something')
        req.body = 'whatever'
        self.assertEquals(req.content_length, 8)
        self.assertEquals(req.body, 'whatever')
        self.assertEquals(req.method, 'GET')

        req.range = 'bytes=1-7'
        self.assertEquals(req.range.ranges[0], (1, 7))

        self.assert_('Range' in req.headers)
        req.range = None
        self.assert_('Range' not in req.headers)

    def test_datetime_properties(self):
        req = swift.common.swob.Request.blank('/hi/there', body='hi')

        req.if_unmodified_since = 0
        self.assert_(isinstance(req.if_unmodified_since, datetime.datetime))
        if_unmodified_since = req.if_unmodified_since
        req.if_unmodified_since = if_unmodified_since
        self.assertEquals(if_unmodified_since, req.if_unmodified_since)

        req.if_unmodified_since = 'something'
        self.assertEquals(req.headers['If-Unmodified-Since'], 'something')
        self.assertEquals(req.if_unmodified_since, None)

        self.assert_('If-Unmodified-Since' in req.headers)
        req.if_unmodified_since = None
        self.assert_('If-Unmodified-Since' not in req.headers)

        too_big_date_list = list(datetime.datetime.max.timetuple())
        too_big_date_list[0] += 1  # bump up the year
        too_big_date = time.strftime(
            "%a, %d %b %Y %H:%M:%S UTC", time.struct_time(too_big_date_list))

        req.if_unmodified_since = too_big_date
        self.assertEqual(req.if_unmodified_since, None)

    def test_bad_range(self):
        req = swift.common.swob.Request.blank('/hi/there', body='hi')
        req.range = 'bad range'
        self.assertEquals(req.range, None)

    def test_accept_header(self):
        req = swift.common.swob.Request({'REQUEST_METHOD': 'GET',
                                         'PATH_INFO': '/',
                                         'HTTP_ACCEPT': 'application/json'})
        self.assertEqual(
            req.accept.best_match(['application/json', 'text/plain']),
            'application/json')
        self.assertEqual(
            req.accept.best_match(['text/plain', 'application/json']),
            'application/json')

    def test_swift_entity_path(self):
        req = swift.common.swob.Request.blank('/v1/a/c/o')
        self.assertEqual(req.swift_entity_path, '/a/c/o')

        req = swift.common.swob.Request.blank('/v1/a/c')
        self.assertEqual(req.swift_entity_path, '/a/c')

        req = swift.common.swob.Request.blank('/v1/a')
        self.assertEqual(req.swift_entity_path, '/a')

        req = swift.common.swob.Request.blank('/v1')
        self.assertEqual(req.swift_entity_path, None)

    def test_path_qs(self):
        req = swift.common.swob.Request.blank('/hi/there?hello=equal&acl')
        self.assertEqual(req.path_qs, '/hi/there?hello=equal&acl')

        req = swift.common.swob.Request({'PATH_INFO': '/hi/there',
                                         'QUERY_STRING': 'hello=equal&acl'})
        self.assertEqual(req.path_qs, '/hi/there?hello=equal&acl')

    def test_url(self):
        req = swift.common.swob.Request.blank('/hi/there?hello=equal&acl')
        self.assertEqual(req.url,
                         'http://localhost/hi/there?hello=equal&acl')

    def test_wsgify(self):
        used_req = []

        @swift.common.swob.wsgify
        def _wsgi_func(req):
            used_req.append(req)
            return swift.common.swob.Response('200 OK')

        req = swift.common.swob.Request.blank('/hi/there')
        resp = req.get_response(_wsgi_func)
        self.assertEqual(used_req[0].path, '/hi/there')
        self.assertEqual(resp.status_int, 200)

    def test_wsgify_raise(self):
        used_req = []

        @swift.common.swob.wsgify
        def _wsgi_func(req):
            used_req.append(req)
            raise swift.common.swob.HTTPServerError()

        req = swift.common.swob.Request.blank('/hi/there')
        resp = req.get_response(_wsgi_func)
        self.assertEqual(used_req[0].path, '/hi/there')
        self.assertEqual(resp.status_int, 500)

    def test_split_path(self):
        """
        Copied from swift.common.utils.split_path
        """
        def _test_split_path(path, minsegs=1, maxsegs=None, rwl=False):
            req = swift.common.swob.Request.blank(path)
            return req.split_path(minsegs, maxsegs, rwl)
        self.assertRaises(ValueError, _test_split_path, '')
        self.assertRaises(ValueError, _test_split_path, '/')
        self.assertRaises(ValueError, _test_split_path, '//')
        self.assertEquals(_test_split_path('/a'), ['a'])
        self.assertRaises(ValueError, _test_split_path, '//a')
        self.assertEquals(_test_split_path('/a/'), ['a'])
        self.assertRaises(ValueError, _test_split_path, '/a/c')
        self.assertRaises(ValueError, _test_split_path, '//c')
        self.assertRaises(ValueError, _test_split_path, '/a/c/')
        self.assertRaises(ValueError, _test_split_path, '/a//')
        self.assertRaises(ValueError, _test_split_path, '/a', 2)
        self.assertRaises(ValueError, _test_split_path, '/a', 2, 3)
        self.assertRaises(ValueError, _test_split_path, '/a', 2, 3, True)
        self.assertEquals(_test_split_path('/a/c', 2), ['a', 'c'])
        self.assertEquals(_test_split_path('/a/c/o', 3), ['a', 'c', 'o'])
        self.assertRaises(ValueError, _test_split_path, '/a/c/o/r', 3, 3)
        self.assertEquals(_test_split_path('/a/c/o/r', 3, 3, True),
                          ['a', 'c', 'o/r'])
        self.assertEquals(_test_split_path('/a/c', 2, 3, True),
                          ['a', 'c', None])
        self.assertRaises(ValueError, _test_split_path, '/a', 5, 4)
        self.assertEquals(_test_split_path('/a/c/', 2), ['a', 'c'])
        self.assertEquals(_test_split_path('/a/c/', 2, 3), ['a', 'c', ''])
        try:
            _test_split_path('o\nn e', 2)
        except ValueError as err:
            self.assertEquals(str(err), 'Invalid path: o%0An%20e')
        try:
            _test_split_path('o\nn e', 2, 3, True)
        except ValueError as err:
            self.assertEquals(str(err), 'Invalid path: o%0An%20e')

    def test_unicode_path(self):
        req = swift.common.swob.Request.blank(u'/\u2661')
        self.assertEquals(req.path, quote(u'/\u2661'.encode('utf-8')))

    def test_unicode_query(self):
        req = swift.common.swob.Request.blank(u'/')
        req.query_string = u'x=\u2661'
        self.assertEquals(req.params['x'], u'\u2661'.encode('utf-8'))

    def test_url2(self):
        pi = '/hi/there'
        path = pi
        req = swift.common.swob.Request.blank(path)
        sche = 'http'
        exp_url = '%s://localhost%s' % (sche, pi)
        self.assertEqual(req.url, exp_url)

        qs = 'hello=equal&acl'
        path = '%s?%s' % (pi, qs)
        s, p = 'unit.test.example.com', '90'
        req = swift.common.swob.Request({'PATH_INFO': pi,
                                         'QUERY_STRING': qs,
                                         'SERVER_NAME': s,
                                         'SERVER_PORT': p})
        exp_url = '%s://%s:%s%s?%s' % (sche, s, p, pi, qs)
        self.assertEqual(req.url, exp_url)

        host = 'unit.test.example.com'
        req = swift.common.swob.Request({'PATH_INFO': pi,
                                         'QUERY_STRING': qs,
                                         'HTTP_HOST': host + ':80'})
        exp_url = '%s://%s%s?%s' % (sche, host, pi, qs)
        self.assertEqual(req.url, exp_url)

        host = 'unit.test.example.com'
        sche = 'https'
        req = swift.common.swob.Request({'PATH_INFO': pi,
                                         'QUERY_STRING': qs,
                                         'HTTP_HOST': host + ':443',
                                         'wsgi.url_scheme': sche})
        exp_url = '%s://%s%s?%s' % (sche, host, pi, qs)
        self.assertEqual(req.url, exp_url)

        host = 'unit.test.example.com:81'
        req = swift.common.swob.Request({'PATH_INFO': pi,
                                         'QUERY_STRING': qs,
                                         'HTTP_HOST': host,
                                         'wsgi.url_scheme': sche})
        exp_url = '%s://%s%s?%s' % (sche, host, pi, qs)
        self.assertEqual(req.url, exp_url)

    def test_as_referer(self):
        pi = '/hi/there'
        qs = 'hello=equal&acl'
        sche = 'https'
        host = 'unit.test.example.com:81'
        req = swift.common.swob.Request({'REQUEST_METHOD': 'POST',
                                         'PATH_INFO': pi,
                                         'QUERY_STRING': qs,
                                         'HTTP_HOST': host,
                                         'wsgi.url_scheme': sche})
        exp_url = '%s://%s%s?%s' % (sche, host, pi, qs)
        self.assertEqual(req.as_referer(), 'POST ' + exp_url)

    def test_message_length_just_content_length(self):
        req = swift.common.swob.Request.blank(
            u'/',
            environ={'REQUEST_METHOD': 'PUT', 'PATH_INFO': '/'})
        self.assertEquals(req.message_length(), None)

        req = swift.common.swob.Request.blank(
            u'/',
            environ={'REQUEST_METHOD': 'PUT', 'PATH_INFO': '/'},
            body='x' * 42)
        self.assertEquals(req.message_length(), 42)

        req.headers['Content-Length'] = 'abc'
        try:
            req.message_length()
        except ValueError as e:
            self.assertEquals(str(e), "Invalid Content-Length header value")
        else:
            self.fail("Expected a ValueError raised for 'abc'")

    def test_message_length_transfer_encoding(self):
        req = swift.common.swob.Request.blank(
            u'/',
            environ={'REQUEST_METHOD': 'PUT', 'PATH_INFO': '/'},
            headers={'transfer-encoding': 'chunked'},
            body='x' * 42)
        self.assertEquals(req.message_length(), None)

        req.headers['Transfer-Encoding'] = 'gzip,chunked'
        try:
            req.message_length()
        except AttributeError as e:
            self.assertEquals(str(e), "Unsupported Transfer-Coding header"
                              " value specified in Transfer-Encoding header")
        else:
            self.fail("Expected an AttributeError raised for 'gzip'")

        req.headers['Transfer-Encoding'] = 'gzip'
        try:
            req.message_length()
        except ValueError as e:
            self.assertEquals(str(e), "Invalid Transfer-Encoding header value")
        else:
            self.fail("Expected a ValueError raised for 'gzip'")

        req.headers['Transfer-Encoding'] = 'gzip,identity'
        try:
            req.message_length()
        except AttributeError as e:
            self.assertEquals(str(e), "Unsupported Transfer-Coding header"
                              " value specified in Transfer-Encoding header")
        else:
            self.fail("Expected an AttributeError raised for 'gzip,identity'")


class TestStatusMap(unittest.TestCase):
    def test_status_map(self):
        response_args = []

        def start_response(status, headers):
            response_args.append(status)
            response_args.append(headers)
        resp_cls = swift.common.swob.status_map[404]
        resp = resp_cls()
        self.assertEquals(resp.status_int, 404)
        self.assertEquals(resp.title, 'Not Found')
        body = ''.join(resp({}, start_response))
        self.assert_('The resource could not be found.' in body)
        self.assertEquals(response_args[0], '404 Not Found')
        headers = dict(response_args[1])
        self.assertEquals(headers['Content-Type'], 'text/html; charset=UTF-8')
        self.assert_(int(headers['Content-Length']) > 0)


class TestResponse(unittest.TestCase):
    def _get_response(self):
        def test_app(environ, start_response):
            start_response('200 OK', [])
            return ['hi']

        req = swift.common.swob.Request.blank('/')
        return req.get_response(test_app)

    def test_properties(self):
        resp = self._get_response()

        resp.location = 'something'
        self.assertEquals(resp.location, 'something')
        self.assert_('Location' in resp.headers)
        resp.location = None
        self.assert_('Location' not in resp.headers)

        resp.content_type = 'text/plain'
        self.assert_('Content-Type' in resp.headers)
        resp.content_type = None
        self.assert_('Content-Type' not in resp.headers)

    def test_empty_body(self):
        resp = self._get_response()
        resp.body = ''
        self.assertEquals(resp.body, '')

    def test_unicode_body(self):
        resp = self._get_response()
        resp.body = u'\N{SNOWMAN}'
        self.assertEquals(resp.body, u'\N{SNOWMAN}'.encode('utf-8'))

    def test_call_reifies_request_if_necessary(self):
        """
        The actual bug was a HEAD response coming out with a body because the
        Request object wasn't passed into the Response object's constructor.
        The Response object's __call__ method should be able to reify a
        Request object from the env it gets passed.
        """
        def test_app(environ, start_response):
            start_response('200 OK', [])
            return ['hi']
        req = swift.common.swob.Request.blank('/')
        req.method = 'HEAD'
        status, headers, app_iter = req.call_application(test_app)
        resp = swift.common.swob.Response(status=status, headers=dict(headers),
                                          app_iter=app_iter)
        output_iter = resp(req.environ, lambda *_: None)
        self.assertEquals(list(output_iter), [''])

    def test_call_preserves_closeability(self):
        def test_app(environ, start_response):
            start_response('200 OK', [])
            yield "igloo"
            yield "shindig"
            yield "macadamia"
            yield "hullabaloo"
        req = swift.common.swob.Request.blank('/')
        req.method = 'GET'
        status, headers, app_iter = req.call_application(test_app)
        iterator = iter(app_iter)
        self.assertEqual('igloo', iterator.next())
        self.assertEqual('shindig', iterator.next())
        app_iter.close()
        self.assertRaises(StopIteration, iterator.next)

    def test_location_rewrite(self):
        def start_response(env, headers):
            pass
        req = swift.common.swob.Request.blank(
            '/', environ={'HTTP_HOST': 'somehost'})
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://somehost/something')

        req = swift.common.swob.Request.blank(
            '/', environ={'HTTP_HOST': 'somehost:80'})
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://somehost/something')

        req = swift.common.swob.Request.blank(
            '/', environ={'HTTP_HOST': 'somehost:443',
                          'wsgi.url_scheme': 'http'})
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://somehost:443/something')

        req = swift.common.swob.Request.blank(
            '/', environ={'HTTP_HOST': 'somehost:443',
                          'wsgi.url_scheme': 'https'})
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'https://somehost/something')

    def test_location_rewrite_no_host(self):
        def start_response(env, headers):
            pass
        req = swift.common.swob.Request.blank(
            '/', environ={'SERVER_NAME': 'local', 'SERVER_PORT': 80})
        del req.environ['HTTP_HOST']
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://local/something')

        req = swift.common.swob.Request.blank(
            '/', environ={'SERVER_NAME': 'local', 'SERVER_PORT': 81})
        del req.environ['HTTP_HOST']
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://local:81/something')

    def test_location_no_rewrite(self):
        def start_response(env, headers):
            pass
        req = swift.common.swob.Request.blank(
            '/', environ={'HTTP_HOST': 'somehost'})
        resp = self._get_response()
        resp.location = 'http://www.google.com/'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, 'http://www.google.com/')

    def test_location_no_rewrite_when_told_not_to(self):
        def start_response(env, headers):
            pass
        req = swift.common.swob.Request.blank(
            '/', environ={'SERVER_NAME': 'local', 'SERVER_PORT': 81,
                          'swift.leave_relative_location': True})
        del req.environ['HTTP_HOST']
        resp = self._get_response()
        resp.location = '/something'
        # read response
        ''.join(resp(req.environ, start_response))
        self.assertEquals(resp.location, '/something')

    def test_app_iter(self):
        def start_response(env, headers):
            pass
        resp = self._get_response()
        resp.app_iter = ['a', 'b', 'c']
        body = ''.join(resp({}, start_response))
        self.assertEquals(body, 'abc')

    def test_multi_ranges_wo_iter_ranges(self):
        def test_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '10')])
            return ['1234567890']

        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=0-9,10-19,20-29'})

        resp = req.get_response(test_app)
        resp.conditional_response = True
        resp.content_length = 10

        # read response
        ''.join(resp._response_iter(resp.app_iter, ''))

        self.assertEquals(resp.status, '200 OK')
        self.assertEqual(10, resp.content_length)

    def test_single_range_wo_iter_range(self):
        def test_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '10')])
            return ['1234567890']

        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=0-9'})

        resp = req.get_response(test_app)
        resp.conditional_response = True
        resp.content_length = 10

        # read response
        ''.join(resp._response_iter(resp.app_iter, ''))

        self.assertEquals(resp.status, '200 OK')
        self.assertEqual(10, resp.content_length)

    def test_multi_range_body(self):
        def test_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '4')])
            return ['abcd']

        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=0-9,10-19,20-29'})

        resp = req.get_response(test_app)
        resp.conditional_response = True
        resp.content_length = 100

        resp.content_type = 'text/plain'
        content = ''.join(resp._response_iter(None,
                                              ('0123456789112345678'
                                               '92123456789')))

        self.assert_(re.match(('\r\n'
                               '--[a-f0-9]{32}\r\n'
                               'Content-Type: text/plain\r\n'
                               'Content-Range: bytes '
                               '0-9/100\r\n\r\n0123456789\r\n'
                               '--[a-f0-9]{32}\r\n'
                               'Content-Type: text/plain\r\n'
                               'Content-Range: bytes '
                               '10-19/100\r\n\r\n1123456789\r\n'
                               '--[a-f0-9]{32}\r\n'
                               'Content-Type: text/plain\r\n'
                               'Content-Range: bytes '
                               '20-29/100\r\n\r\n2123456789\r\n'
                               '--[a-f0-9]{32}--\r\n'), content))

    def test_multi_response_iter(self):
        def test_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '10'),
                                      ('Content-Type', 'application/xml')])
            return ['0123456789']

        app_iter_ranges_args = []

        class App_iter(object):
            def app_iter_ranges(self, ranges, content_type, boundary, size):
                app_iter_ranges_args.append((ranges, content_type, boundary,
                                             size))
                for i in xrange(3):
                    yield str(i) + 'fun'
                yield boundary

            def __iter__(self):
                for i in xrange(3):
                    yield str(i) + 'fun'

        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=1-5,8-11'})

        resp = req.get_response(test_app)
        resp.conditional_response = True
        resp.content_length = 12

        content = ''.join(resp._response_iter(App_iter(), ''))
        boundary = content[-32:]
        self.assertEqual(content[:-32], '0fun1fun2fun')
        self.assertEqual(app_iter_ranges_args,
                         [([(1, 6), (8, 12)], 'application/xml',
                           boundary, 12)])

    def test_range_body(self):

        def test_app(environ, start_response):
            start_response('200 OK', [('Content-Length', '10')])
            return ['1234567890']

        def start_response(env, headers):
            pass

        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=1-3'})

        resp = swift.common.swob.Response(
            body='1234567890', request=req,
            conditional_response=True)
        body = ''.join(resp([], start_response))
        self.assertEquals(body, '234')
        self.assertEquals(resp.content_range, 'bytes 1-3/10')
        self.assertEquals(resp.status, '206 Partial Content')

        # syntactically valid, but does not make sense, so returning 416
        # in next couple of cases.
        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=-0'})
        resp = req.get_response(test_app)
        resp.conditional_response = True
        body = ''.join(resp([], start_response))
        self.assertEquals(body, '')
        self.assertEquals(resp.content_length, 0)
        self.assertEquals(resp.status, '416 Requested Range Not Satisfiable')

        resp = swift.common.swob.Response(
            body='1234567890', request=req,
            conditional_response=True)
        body = ''.join(resp([], start_response))
        self.assertEquals(body, '')
        self.assertEquals(resp.content_length, 0)
        self.assertEquals(resp.status, '416 Requested Range Not Satisfiable')

        # Syntactically-invalid Range headers "MUST" be ignored
        req = swift.common.swob.Request.blank(
            '/', headers={'Range': 'bytes=3-2'})
        resp = req.get_response(test_app)
        resp.conditional_response = True
        body = ''.join(resp([], start_response))
        self.assertEquals(body, '1234567890')
        self.assertEquals(resp.status, '200 OK')

        resp = swift.common.swob.Response(
            body='1234567890', request=req,
            conditional_response=True)
        body = ''.join(resp([], start_response))
        self.assertEquals(body, '1234567890')
        self.assertEquals(resp.status, '200 OK')

    def test_content_type(self):
        resp = self._get_response()
        resp.content_type = 'text/plain; charset=utf8'
        self.assertEquals(resp.content_type, 'text/plain')

    def test_charset(self):
        resp = self._get_response()
        resp.content_type = 'text/plain; charset=utf8'
        self.assertEquals(resp.charset, 'utf8')
        resp.charset = 'utf16'
        self.assertEquals(resp.charset, 'utf16')

    def test_charset_content_type(self):
        resp = swift.common.swob.Response(
            content_type='text/plain', charset='utf-8')
        self.assertEquals(resp.charset, 'utf-8')
        resp = swift.common.swob.Response(
            charset='utf-8', content_type='text/plain')
        self.assertEquals(resp.charset, 'utf-8')

    def test_etag(self):
        resp = self._get_response()
        resp.etag = 'hi'
        self.assertEquals(resp.headers['Etag'], '"hi"')
        self.assertEquals(resp.etag, 'hi')

        self.assert_('etag' in resp.headers)
        resp.etag = None
        self.assert_('etag' not in resp.headers)

    def test_host_url_default(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'http'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '1234'
        del env['HTTP_HOST']
        self.assertEquals(resp.host_url, 'http://bob:1234')

    def test_host_url_default_port_squelched(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'http'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '80'
        del env['HTTP_HOST']
        self.assertEquals(resp.host_url, 'http://bob')

    def test_host_url_https(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'https'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '1234'
        del env['HTTP_HOST']
        self.assertEquals(resp.host_url, 'https://bob:1234')

    def test_host_url_https_port_squelched(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'https'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '443'
        del env['HTTP_HOST']
        self.assertEquals(resp.host_url, 'https://bob')

    def test_host_url_host_override(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'http'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '1234'
        env['HTTP_HOST'] = 'someother'
        self.assertEquals(resp.host_url, 'http://someother')

    def test_host_url_host_port_override(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'http'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '1234'
        env['HTTP_HOST'] = 'someother:5678'
        self.assertEquals(resp.host_url, 'http://someother:5678')

    def test_host_url_host_https(self):
        resp = self._get_response()
        env = resp.environ
        env['wsgi.url_scheme'] = 'https'
        env['SERVER_NAME'] = 'bob'
        env['SERVER_PORT'] = '1234'
        env['HTTP_HOST'] = 'someother:5678'
        self.assertEquals(resp.host_url, 'https://someother:5678')

    def test_507(self):
        resp = swift.common.swob.HTTPInsufficientStorage()
        content = ''.join(resp._response_iter(resp.app_iter, resp._body))
        self.assertEquals(
            content,
            '<html><h1>Insufficient Storage</h1><p>There was not enough space '
            'to save the resource. Drive: unknown</p></html>')
        resp = swift.common.swob.HTTPInsufficientStorage(drive='sda1')
        content = ''.join(resp._response_iter(resp.app_iter, resp._body))
        self.assertEquals(
            content,
            '<html><h1>Insufficient Storage</h1><p>There was not enough space '
            'to save the resource. Drive: sda1</p></html>')


class TestUTC(unittest.TestCase):
    def test_tzname(self):
        self.assertEquals(swift.common.swob.UTC.tzname(None), 'UTC')


class TestConditionalIfNoneMatch(unittest.TestCase):
    def fake_app(self, environ, start_response):
        start_response('200 OK', [('Etag', 'the-etag')])
        return ['hi']

    def fake_start_response(*a, **kw):
        pass

    def test_simple_match(self):
        # etag matches --> 304
        req = swift.common.swob.Request.blank(
            '/', headers={'If-None-Match': 'the-etag'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')

    def test_quoted_simple_match(self):
        # double quotes don't matter
        req = swift.common.swob.Request.blank(
            '/', headers={'If-None-Match': '"the-etag"'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')

    def test_list_match(self):
        # it works with lists of etags to match
        req = swift.common.swob.Request.blank(
            '/', headers={'If-None-Match': '"bert", "the-etag", "ernie"'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')

    def test_list_no_match(self):
        # no matches --> whatever the original status was
        req = swift.common.swob.Request.blank(
            '/', headers={'If-None-Match': '"bert", "ernie"'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_match_star(self):
        # "*" means match anything; see RFC 2616 section 14.24
        req = swift.common.swob.Request.blank(
            '/', headers={'If-None-Match': '*'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')


class TestConditionalIfMatch(unittest.TestCase):
    def fake_app(self, environ, start_response):
        start_response('200 OK', [('Etag', 'the-etag')])
        return ['hi']

    def fake_start_response(*a, **kw):
        pass

    def test_simple_match(self):
        # if etag matches, proceed as normal
        req = swift.common.swob.Request.blank(
            '/', headers={'If-Match': 'the-etag'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_quoted_simple_match(self):
        # double quotes or not, doesn't matter
        req = swift.common.swob.Request.blank(
            '/', headers={'If-Match': '"the-etag"'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_no_match(self):
        # no match --> 412
        req = swift.common.swob.Request.blank(
            '/', headers={'If-Match': 'not-the-etag'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 412)
        self.assertEquals(body, '')

    def test_match_star(self):
        # "*" means match anything; see RFC 2616 section 14.24
        req = swift.common.swob.Request.blank(
            '/', headers={'If-Match': '*'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_match_star_on_404(self):

        def fake_app_404(environ, start_response):
            start_response('404 Not Found', [])
            return ['hi']

        req = swift.common.swob.Request.blank(
            '/', headers={'If-Match': '*'})
        resp = req.get_response(fake_app_404)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 412)
        self.assertEquals(body, '')


class TestConditionalIfModifiedSince(unittest.TestCase):
    def fake_app(self, environ, start_response):
        start_response(
            '200 OK', [('Last-Modified', 'Thu, 27 Feb 2014 03:29:37 GMT')])
        return ['hi']

    def fake_start_response(*a, **kw):
        pass

    def test_absent(self):
        req = swift.common.swob.Request.blank('/')
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_before(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Modified-Since': 'Thu, 27 Feb 2014 03:29:36 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_same(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Modified-Since': 'Thu, 27 Feb 2014 03:29:37 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')

    def test_greater(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Modified-Since': 'Thu, 27 Feb 2014 03:29:38 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 304)
        self.assertEquals(body, '')

    def test_out_of_range_is_ignored(self):
        # All that datetime gives us is a ValueError or OverflowError when
        # something is out of range (i.e. less than datetime.datetime.min or
        # greater than datetime.datetime.max). Unfortunately, we can't
        # distinguish between a date being too old and a date being too new,
        # so the best we can do is ignore such headers.
        max_date_list = list(datetime.datetime.max.timetuple())
        max_date_list[0] += 1  # bump up the year
        too_big_date_header = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.struct_time(max_date_list))

        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Modified-Since': too_big_date_header})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')


class TestConditionalIfUnmodifiedSince(unittest.TestCase):
    def fake_app(self, environ, start_response):
        start_response(
            '200 OK', [('Last-Modified', 'Thu, 20 Feb 2014 03:29:37 GMT')])
        return ['hi']

    def fake_start_response(*a, **kw):
        pass

    def test_absent(self):
        req = swift.common.swob.Request.blank('/')
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_before(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Unmodified-Since': 'Thu, 20 Feb 2014 03:29:36 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 412)
        self.assertEquals(body, '')

    def test_same(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Unmodified-Since': 'Thu, 20 Feb 2014 03:29:37 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_greater(self):
        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Unmodified-Since': 'Thu, 20 Feb 2014 03:29:38 GMT'})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')

    def test_out_of_range_is_ignored(self):
        # All that datetime gives us is a ValueError or OverflowError when
        # something is out of range (i.e. less than datetime.datetime.min or
        # greater than datetime.datetime.max). Unfortunately, we can't
        # distinguish between a date being too old and a date being too new,
        # so the best we can do is ignore such headers.
        max_date_list = list(datetime.datetime.max.timetuple())
        max_date_list[0] += 1  # bump up the year
        too_big_date_header = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.struct_time(max_date_list))

        req = swift.common.swob.Request.blank(
            '/',
            headers={'If-Unmodified-Since': too_big_date_header})
        resp = req.get_response(self.fake_app)
        resp.conditional_response = True
        body = ''.join(resp(req.environ, self.fake_start_response))
        self.assertEquals(resp.status_int, 200)
        self.assertEquals(body, 'hi')


if __name__ == '__main__':
    unittest.main()
