#!/usr/bin/python
#
# Tool for generating a high level summary of a test output folder
# Copyright (c) 2013, Intel Corporation.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms and conditions of the GNU General Public License,
# version 2, as published by the Free Software Foundation.
#
# This program is distributed in the hope it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St - Fifth Floor, Boston, MA 02110-1301 USA.
#
# Authors:
#	 Todd Brandt <todd.e.brandt@intel.com>
#

import sys
import os
import re
import argparse
import smtplib
sys.path += ['..', '.']
import sleepgraph as sg

def dmesg_issues(file, errinfo):
	errlist = sg.Data.errlist
	lf = sg.sysvals.openlog(file, 'r')
	i = 0
	list = []
	for line in lf:
		i += 1
		m = re.match('[ \t]*(\[ *)(?P<ktime>[0-9\.]*)(\]) (?P<msg>.*)', line)
		if not m:
			continue
		t = float(m.group('ktime'))
		msg = m.group('msg')
		for err in errlist:
			if re.match(errlist[err], msg):
				if err not in errinfo:
					errinfo[err] = []
				found = False
				for entry in errinfo[err]:
					if re.match(entry['match'], msg):
						entry['count'] += 1
						found = True
						break
				if found:
					continue
				arr = msg.split()
				for j in range(len(arr)):
					if re.match('^[0-9\-\.]*$', arr[j]):
						arr[j] = '[0-9\-\.]*'
					else:
						arr[j] = arr[j].replace(']', '\]').replace('[', '\[').replace('.', '\.').replace('+', '\+')
				mstr = ' '.join(arr)
				entry = {
					'line': msg,
					'match': mstr,
					'count': 1,
					'url': os.path.abspath(file)
				}
				errinfo[err].append(entry)
				break

def info(file, data, errcheck):
	html = open(file, 'r').read()
	line = sg.find_in_html(html, '<div class="stamp">', '</div>')
	x = re.match('^(?P<host>.*) (?P<kernel>.*) (?P<mode>.*) \((?P<info>.*)\)', line)
	if not x:
		print 'WARNING: unrecognized formatting in summary file' % file
		return
	h, k, m, r = x.groups()
	errinfo = dict()
	res = []
	total = -1
	for i in re.findall(r"[\w ]+", r):
		item = i.strip().split()
		if len(item) != 2:
			continue
		if item[1] == 'tests':
			total = float(item[0])
		elif total > 0:
			p = 100*float(item[0])/total
			res.append('%s: %s/%.0f (%.1f%%)' % (item[1].upper(), item[0], total, p))
	if k not in data:
		data[k] = dict()
	if h not in data[k]:
		data[k][h] = dict()
	if m not in data[k][h]:
		data[k][h][m] = dict()
	smax = sg.find_in_html(html, '<a href="#s%smax">' % m, '</a>')
	smed = sg.find_in_html(html, '<a href="#s%smed">' % m, '</a>')
	smin = sg.find_in_html(html, '<a href="#s%smin">' % m, '</a>')
	rmax = sg.find_in_html(html, '<a href="#r%smax">' % m, '</a>')
	rmed = sg.find_in_html(html, '<a href="#r%smed">' % m, '</a>')
	rmin = sg.find_in_html(html, '<a href="#r%smin">' % m, '</a>')
	wres = dict()
	wsus = dict()
	for test in html.split('<tr'):
		if '<th>' in test or 'class="head"' in test or '<html>' in test:
			continue
		dmesg = ''
		values = []
		out = test.split('<td')
		for i in out[1:]:
			values.append(i[1:].replace('</td>', '').replace('</tr>', '').strip())
		if values[9]:
			if values[9] not in wsus:
				wsus[values[9]] = 0
			wsus[values[9]] += 1
		if values[11]:
			if values[11] not in wres:
				wres[values[11]] = 0
			wres[values[11]] += 1
		if not errcheck:
			continue
		if values[13]:
			x = re.match('<a href="(?P<u>.*)">', values[13])
			dcheck = file.replace('summary.html', x.group('u').replace('.html', '_dmesg.txt.gz'))
			if os.path.exists(dcheck):
				dmesg = dcheck
			elif os.path.exists(dmesg[:-3]):
				dmesg = dcheck[:-3]
		if values[6] and values[6] != 'NETLOST' and dmesg:
			dmesg_issues(dmesg, errinfo)
	wstext = dict()
	for i in sorted(wsus, key=lambda k:wsus[k], reverse=True):
		wstext[wsus[i]] = i
	wrtext = dict()
	for i in sorted(wres, key=lambda k:wres[k], reverse=True):
		wrtext[wres[i]] = i
	issues = dict()
	for err in errinfo:
		for entry in errinfo[err]:
			issues[entry['count']] = entry
	data[k][h][m] = {
		'file': file,
		'results': res,
		'sstat': [smax, smed, smin],
		'rstat': [rmax, rmed, rmin],
		'wsd': wstext,
		'wrd': wrtext,
		'issues': issues
	}

def text_output(data):
	text = ''
	for kernel in sorted(data):
		text += 'Sleepgraph stress test results for kernel %s (%d machines)\n' % \
			(kernel, len(data[kernel].keys()))
		for host in sorted(data[kernel]):
			text += '\n[%s]\n' % host
			for mode in sorted(data[kernel][host], reverse=True):
				info = data[kernel][host][mode]
				text += '%s:\n' % mode.upper()
				text += '   ' + ', '.join(info['results']) + '\n'
				text += '   Suspend: %s, %s, %s\n' % \
					(info['sstat'][0], info['sstat'][1], info['sstat'][2])
				text += '   Resume: %s, %s, %s\n' % \
					(info['rstat'][0], info['rstat'][1], info['rstat'][2])
				text += '   Worst Suspend Devices:\n'
				for cnt in sorted(info['wsd'], reverse=True):
					text += '   - %s (%d times)\n' % (info['wsd'][cnt], cnt)
				text += '   Worst Resume Devices:\n'
				for cnt in sorted(info['wrd'], reverse=True):
					text += '   - %s (%d times)\n' % (info['wrd'][cnt], cnt)
				issues = info['issues']
				if len(issues) < 1:
					continue
				text += '   Issues found in dmesg logs:\n'
				for e in sorted(issues, reverse=True):
					text += '   (x%d) %s\n' % (e, issues[e]['line'])
	return text

def get_url(dmesgfile, urlprefix):
	html = dmesgfile.replace('.gz', '').replace('_dmesg.txt', '.html')
	idx = html.find('pm-graph-test')
	if not urlprefix or idx < 0:
		return '<a href="file://%s">html</a>' % html
	idx += len('pm-graph-test')
	return '<a href="%s">html</a>' % (urlprefix+html[idx:])

def html_output(data, urlprefix, showerrs):
	html = '<!DOCTYPE html>\n<html>\n<head>\n\
		<meta http-equiv="content-type" content="text/html; charset=UTF-8">\n\
		<title>SleepGraph Summary of Summaries</title>\n\
		<style type=\'text/css\'>\n\
			table {width:100%; border-collapse: collapse;}\n\
			.summary {border:0px solid;}\n\
			th {border: 1px solid black;background:#222;color:white;}\n\
			td {font: 14px "Times New Roman";}\n\
			td.devlist {padding: 0;}\n\
			ul {list-style-type: none;}\n\
			ul.devlist {list-style-type: circle; font-size: 12px;}\n\
			tr.alt {background-color:#ddd;}\n\
		</style>\n</head>\n<body>\n'

	th = '\t<th>{0}</th>\n'
	td = '\t<td nowrap>{0}</td>\n'
	tdo = '\t<td nowrap{1}>{0}</td>\n'

	for kernel in sorted(data):
		html += 'Sleepgraph stress test results for kernel %s (%d machines)<br><br>\n' % \
			(kernel, len(data[kernel].keys()))
		html += '<table class="summary">\n<tr>\n' + th.format('Host') +\
			th.format('Mode') + th.format('Results') + th.format('Suspend Time') +\
			th.format('Resume Time') + th.format('Worst Suspend Devices') +\
			th.format('Worst Resume Devices') + '</tr>\n'
		num = 0
		for host in sorted(data[kernel]):
			for mode in sorted(data[kernel][host], reverse=True):
				trs = '<tr class=alt>\n' if num % 2 == 1 else '<tr>\n'
				html += trs
				info = data[kernel][host][mode]
				html += tdo.format(host, ' align=center')
				html += td.format(mode)
				tdhtml = '<table>'
				for val in info['results']:
					tdhtml += '<tr><td nowrap>%s</td></tr>' % val
				html += td.format(tdhtml+'</table>')
				for entry in ['sstat', 'rstat']:
					tdhtml = '<table>'
					for val in info[entry]:
						tdhtml += '<tr><td nowrap>%s</td></tr>' % val
					html += td.format(tdhtml+'</table>')
				for entry in ['wsd', 'wrd']:
					tdhtml = '<ul class=devlist>'
					for cnt in sorted(info[entry], reverse=True):
						tdhtml += '<li>%s (x%d)</li>' % (info[entry][cnt], cnt)
					html += tdo.format(tdhtml+'</ul>', ' class=devlist')
				html += '</tr>\n'
				if not showerrs:
					continue
				html += '%s<td colspan=7><table border=1>' % trs
				html += '%s<td colspan=5><b>Issues found</b></td><td><b>Count</b></td><td><b>html</b></td>\n</tr>' % trs
				issues = info['issues']
				if len(issues) > 0:
					for e in sorted(issues, reverse=True):
						html += '%s<td colspan=5>%s</td><td>%d times</td><td>%s</td>\n<tr>\n' % \
							(trs, issues[e]['line'], e, get_url(issues[e]['url'], urlprefix))
				else:
					html += '%s<td colspan=7>NONE</td>\n<tr>\n' % trs
				html += '</table></td></tr>'
			num += 1
		html += '</table>\n'
	html += '</body>\n</html>\n'
	return html

def send_mail(server, sender, receiver, type, subject, contents):
	message = \
		'From: %s\n'\
		'To: %s\n'\
		'MIME-Version: 1.0\n'\
		'Content-type: %s\n'\
		'Subject: %s\n\n' % (sender, receiver, type, subject)
	receivers = receiver.split(';')
	message += contents
	smtpObj = smtplib.SMTP(server, 25)
	smtpObj.sendmail(sender, receivers, message)

def doError(msg, help=False):
	print("ERROR: %s") % msg
	if(help == True):
		printHelp()
	sys.exit()

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Generate a summary of a summaries')
	parser.add_argument('--html', action='store_true',
		help='output in html (default is text)')
	parser.add_argument('--issues', action='store_true',
		help='extract issues from dmesg files (WARNING/ERROR etc)')
	parser.add_argument('--mail', nargs=3, metavar=('server', 'sender', 'receiver'),
		help='send the output via email')
	parser.add_argument('--subject', metavar='string',
		help='the subject line for the email')
	parser.add_argument('--urlprefix', metavar='url',
		help='url prefix to use in links to timelines')
	parser.add_argument('folder', help='folder to search for summaries')
	args = parser.parse_args()

	if not os.path.exists(args.folder) or not os.path.isdir(args.folder):
		doError('Folder not found')

	if args.urlprefix:
		if args.urlprefix[-1] == '/':
			args.urlprefix = args.urlprefix[:-1]
		if not args.urlprefix.endswith('pm-graph-test') :
			doError('urlprefix must end with pm-graph-test')

	data = dict()
	for dirname, dirnames, filenames in os.walk(args.folder):
		for filename in filenames:
			if filename == 'summary.html':
				file = os.path.join(dirname, filename)
				info(file, data, args.issues)

	out = html_output(data, args.urlprefix, args.issues) if args.html else text_output(data)

	if args.mail:
		server, sender, receiver = args.mail
		subject = args.subject if args.subject else 'Summary of sleepgraph batch tests'
		type = 'text/html' if args.html else 'text'
		send_mail(server, sender, receiver, type, subject, out)
	else:
		print out