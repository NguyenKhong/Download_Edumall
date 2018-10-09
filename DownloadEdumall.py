# -*- coding: utf-8 -*-
import requests
import os
import sys
import re
from bs4 import BeautifulSoup
import time
import timeit
from urlparse import urljoin
import unicodedata
import datetime
import ntpath
from Crypto.Cipher import AES
import struct
import shutil
import ffmpeg
import threading
import urllib
import logging
import ctypes

reload(sys)
sys.setdefaultencoding('utf-8')
os.environ['HTTPSVERIFY'] = '0'

g_session = requests.Session()

g_UserAgent = 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:44.0) Gecko/20100101 Firefox/44.0'
g_CurrentDir = os.getcwd()
g_Key = None
kernel32 = ctypes.windll.kernel32



logger = logging.getLogger(__name__)

stdout_logger = logging.StreamHandler()
file_logger = logging.FileHandler("DownloadEdumall.log", mode = 'w')
formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
stdout_logger.setFormatter(formatter)
file_logger.setFormatter(formatter)

logger.addHandler(stdout_logger)
logger.addHandler(file_logger)
logger.setLevel(logging.INFO)


def NoAccentVietnamese(s):
    s = s.decode('utf-8')
    s = re.sub(u'Đ', 'D', s)
    s = re.sub(u'đ', 'd', s)
    return unicodedata.normalize('NFKD', unicode(s)).encode('ASCII', 'ignore')

def Login(User, Pass):
	'''
	Name..........: Login
	Description...: Login edumall.vn
	Parameters....: User - string. User name
	..............: Pass - string. Password
	Return values.: None
	Author........: Zero-0
	'''
	url = 'https://edumall.vn'
	try:
		r = g_session.get(url)
		if r.status_code != 200:
			logger.critical("Loi server")
			sys.exit(1)
	except Exception as e:
		logger.critical("Loi: %s - url: %s", e, url)
		return False

	authenticity_token = re.findall(r'"authenticity_token".*value="(.*?)"', r.content)
	if not authenticity_token:
		logger.critical("Vui long lien he nha phat trien")
		return False

	payload = { 'user[email]' : User,
				'user[password]': Pass,
				'authenticity_token' : authenticity_token[1]
		}
	try:
		url = 'https://edumall.vn/users/sign_in'
		r = g_session.post(url, data = payload)
		if r.status_code != 200:
			logger.warning("Loi dang nhap")
	except Exception as e:
		logger.critical("Loi: %s - url: %s", e, url)
		return False

	if r.content.find(u'Email hoặc mật khẩu không chính xác') != -1:
		print ("Email hoac mat khau khong chinh xac")
		return False
	return True

def GetCourses():
	'''
	Name..........: GetCourses
	Description...: Get list of courses
	Parameters....: None
	Return values.: Success - Returns list with 2 element:
	................| list[0] - url of course
	................| list[1] - name of course
	..............: Failure - Returns list is None
	Author........: Zero-0
	'''
	url = 'https://edumall.vn/users/my_courses'
	try:
		r = g_session.get(url)
		if r.status_code != 200:
			return []
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
		return []

	soup = BeautifulSoup(r.content, 'html5lib')
	courses = soup.findAll('div', {'class': 'learning-card'})
	if courses == []:
		logger.warning("Loi Phan tich khoa hoc")
		return []

	UrlCourses = []
	for course in courses:
		name = course.a.find('div', {'class' : 'row ellipsis-2lines course-title'}).text
		if name == []:
			logger.warning("Loi Phan tich tieu de khoa hoc")
			return []
		UrlCourses.append((urljoin(url, course.a['href']), NoAccentVietnamese(name).strip()))

	return UrlCourses

def GetLessions(url):
	'''
	Name..........: GetLessions
	Description...: Get list of Lessions
	Parameters....: url - string. Url get from function GetCourses()
	Return values.: Success - Returns list with 2 element:
	................| list[0] - url of Lession
	................| list[1] - name of Lession
	..............: Failure - Returns list is None
	Author........: Zero-0
	'''
	try:
		r = g_session.get(url)
		if r.status_code != 200:
			return []
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
		return []

	soup = BeautifulSoup(r.content, 'html5lib')
	Menu = soup.find('div', {'class' : 'menu'})
	
	buttonBuy = soup.findAll('a', {'class' : 'btn-red btn-buy'})
	if buttonBuy:
		print "Khoa hoc nay chua mua."
		return [] 
	if not Menu:
		logger.warning('Loi Khong the phan tich toan bo bai giang nay')
		return []
	if not Menu.a.get('href'):
		logger.warning('Loi Thieu url de phan tich bai giang')
		return []
	url = urljoin(url, Menu.a.get('href'))
	try:
		r = g_session.get(url)
		if r.status_code != 200:
			return []
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
		return []
	soup = BeautifulSoup(r.content, 'html5lib')	
	Lessions = soup.findAll('div', {'class' : re.compile('^row chap-item')})
	if not Lessions:
		logger.warning('Loi Khong the lay danh sach bai giang')
		return []
	UrlLessions = []
	for lession in Lessions:
		name = lession.find('div', {'class' : 'row no-margin'})
		if not name:
			logger.warning("Loi Phan tich Ten bai giang")
			return []
		name = name.text
		for x in list('\/:*?"<>|'): name = name.replace(x, '')
		UrlLessions.append((urljoin(url, lession.a.get('href')), NoAccentVietnamese(name).strip()))
	return UrlLessions 

def GetUrlMasterPlaylistFromLession(url, IsGetLinkDocument = True):
	'''
	Name..........: GetUrlMasterPlaylistFromLession
	Description...: Get url of video
	Parameters....: url - string. Url get from function GetLessions()
				  : IsGetLinkDocument - Bool. Get urls of documnets in Lession.
	Return values.: Success - Returns url Master Playlist and url of documents
	..............: Failure - Returns None
	Author........: Zero-0
	'''
	try:
		r = g_session.get(url)
		if r.status_code != 200:
			return "", []
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
		return "", []

	UrlMasterPlayList = re.findall(r'jw_video_url\s=\s"(.*)"', r.content)
	if UrlMasterPlayList:
		if IsGetLinkDocument:
			soup = BeautifulSoup(r.content, 'html5lib')
			documentDownload = soup.find('div', {'id': 'lecture-tab-download'})
			urlDocuments = [] 
			if documentDownload.text.find(u'Tài liệu của bài học') != -1:
				for i in documentDownload.findAll('li'):
					urlDocuments.append(urljoin(url, i.a.get('href'))) 
			return UrlMasterPlayList[0], urlDocuments
		return UrlMasterPlayList[0], []
	else:
		if r.content.find('Use video from youtube') != -1:
			print "Video nay co nguon tu youtube. Vui long len trang edumall de lay link."
	return "", []

def GetM3u8HD(url):
	'''
	Name..........: GetM3u8HD
	Description...: Get url of video HD
	Parameters....: url - string. Url get from function GetUrlMasterPlaylistFromLession()
	Return values.: Success - Returns url video HD
	..............: Failure - Returns None
	Author........: Zero-0
	link example..: https://tools.ietf.org/html/draft-pantos-http-live-streaming-20#section-8.4
	'''
	if url == "":
		return ""
	try:
		r = requests.get(url, headers = {'User-Agent' : g_UserAgent})
		if r.status_code != 200:
			return ""
		streamInfo = re.findall(r"#EXT-X-STREAM-INF:.*?BANDWIDTH=(\d+).*?\n([\w\d$-_.+!*\'\(\),]+)", r.content)
		if streamInfo:
			BandWidth = map(int, [x[0] for x in streamInfo])
			if BandWidth:
				return urljoin(url, streamInfo[BandWidth.index(max(BandWidth))][1]) 
	except Exception as e:
		logger.warning("Loi %s - url: %s", e, url)
	return ""

def GetPlaylist(url, IsDownloadKey = False, pathLocal = None):
	'''
	Name..........: GetPlaylist
	Description...: Get list of file ts And get URI contain key store on server
	Parameters....: url - string. Url get from function GetM3u8HD()
	..............: IsDownloadKey - [optional] If true function will get url contain key
	..............: pathLocal - [optional] path to directiory save key on client
	Return values.: Success - Returns list with element contains url of file ts
	..............: Failure - Returns None
	Author........: Zero-0
	Link example..: https://tools.ietf.org/html/draft-pantos-http-live-streaming-20#section-8
	'''
	if url == "":
		return []
	try:
		r = requests.get(url, headers = {'User-Agent' : g_UserAgent})
		if r.status_code != 200:
			return []
	except Exception as e:
		logger.warning("Loi %s - url: %s", e, url)
		return []

	global g_Key
	g_Key = None
	try:
		if IsDownloadKey and ('#EXT-X-KEY' in r.content):
			#key = {}
			#result = re.findall(r'(\w+)=("[^"]*"|[^,"#]*)', r.content)
			#for attrib, value in result:
			#	key[attrib] = value.replace('"', '')
			#if 'URI' in key:
			#	print timeit.default_timer() - start
			#	GetKey(urljoin(url, key['URI']), pathLocal)

			result = re.findall(r'URI="(.*?)"', r.content)
			urlKey = ""
			if result:
				if result[0].startswith('http'):
					urlKey = result[0]
				else:
					urlKey = urljoin(url, result[0])
				for i in xrange(5):	
					if GetKey(urlKey, pathLocal) != "":
						break
					time.sleep(3)
	except Exception as e:
		logger.warning("Loi: %s - Get URI Key Failed", e)

	listUrlTs = []
	listTs = re.findall(r'#EXTINF:[\d.]+,\n([\w\d$-_.+!*\'\(\),]+)\n', r.content)
	if listTs:
		for item in listTs:
			listUrlTs.append(urljoin(url, item))
	return listUrlTs

def GetKey(url, pathLocal = None):
	'''
	Name..........: GetKey
	Description...: Download Key from server to client and save it
	Parameters....: url - string. Url get from function GetPlaylist()
	..............: pathLocal - [optional] path to directiory save key on client
	Return values.: Success - Returns Binary key
	..............: Failure - Returns list is None
	Author........: Zero-0
	'''
	if not pathLocal: pathLocal = g_CurrentDir
	fileName = 'key_%s.key' % datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d-%H-%M-%S')
	try:
		r = requests.get(url, headers = {'User-Agent' : g_UserAgent})
		if r.status_code != 200:
			logger.warning("Download Key Failed - Loi Server: {%s}.", r.status_code)
			return ""
	except Exception as e:
		logger.warning("Download Key Failed - Loi: {%s} - url: %s.", e, url)
		return ""

	global g_Key
	g_Key = None
	if len(r.content)%16:
		logger.warning("Download key Failed - Khoa khong du du lieu.")
		g_Key = None
		return ""
	g_Key = r.content
	with open(os.path.join(pathLocal, fileName), 'wb') as f:
		for chunk in r.iter_content(1024):
			f.write(chunk)
	print (fileName)
	return r.content
	
def DownloadTs(url, pathLocal, IsDecrypt = True):
	'''
	Name..........: DownloadTs
	Description...: Download file ts from server to client and save it
	Parameters....: url - string. Url get from function GetPlaylist()
	..............: pathLocal - string. Path to directiory save file ts on client
	..............: IsDecrypt - [optional] If true function will decrypt file ts
	Return values.: None
	Author........: Zero-0
	'''
	try:
		tmp = re.findall(r"[_|-](\d+\.ts)", urllib.unquote(url))
		fileName = tmp[0]
	except:
		fileName = pathLeaf(urllib.unquote(url))
	fileName = removeCharacters(fileName)
	try:
		r = requests.get(url, headers = {'User-Agent' : g_UserAgent}, stream = True)
		if r.status_code != 200:
			logger.warning("Loi: %s - url: %s", r.status_code, url)
			return False
		print fileName
		with open(os.path.join(pathLocal, fileName), 'wb') as f:
			if IsDecrypt and g_Key:
				data = Decrypt(r.content, g_Key)
				if data:
					f.write(data)
			else:
				for chunk in r.iter_content(1048576):
					f.write(chunk)
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
		return False
	return True		

def DownloadTss(urls, pathLocal, IsDecrypt = True):
	for url in urls:
		for i in xrange(5):
			if DownloadTs(url, pathLocal):
				break
			time.sleep(1)

def DownloadDocument(url, pathLocal):
	'''
	Name..........: DownloadDocument
	Description...: Download file document from server to client and save it
	Parameters....: url - string. Url get from function GetUrlMasterPlaylistFromLession()
	..............: pathLocal - string. Path to directiory save file on client
	Return values.: None
	Author........: Zero-0
	'''
	try:
		r = g_session.get(url, stream = True)
		if r.status_code != 200:
			return False

		fileName = pathLeaf(urllib.unquote(url)).encode('utf-8')
		fileName = removeCharacters(fileName)
		with open(os.path.join(pathLocal, fileName), 'wb') as f:
			for chunk in r.iter_content(5242880):
				f.write(chunk)
		print fileName
	except Exception as e:
		logger.warning("Loi: %s - url: %s", e, url)
	return True

def DownloadDocuments(urls, pathLocal):
	for url in urls:
		for i in xrange(5):
			if DownloadDocument(url, pathLocal):
				break
			time.sleep(1)

def Decrypt(data, key, IV = None):
	'''
	Name..........: Decrypt
	Description...: Decrypt file ts
	Parameters....: data - binary. Get from function DownloadTs()
	..............: key - binary. Get from function GetKey()
	..............: IV - [optional]. Cryptography AES
	Return values.: None
	Author........: Zero-0
	'''
	if len(key)%16:
		logger.warning("Khong the giai ma file ts - Khoa khong du du lieu.")
		return ""
	if IV is None:
		IV = data[0:16]
		data = data[16:]
	dataLen = len(data)
	decryptor = AES.new(key, AES.MODE_CBC, IV)
	chunksize = 64*1024
	dataOut = b''
	i = 0
	while True:
		chunk = data[i:i+chunksize]
		i += len(chunk)
		if i >= dataLen:
			chunk = decryptor.decrypt(chunk)
			chunk = RemovePadding(chunk)
			dataOut += chunk
			break
		else:
			dataOut += decryptor.decrypt(chunk)
	return dataOut

def pathLeaf(path):
	'''
	Name..........: pathLeaf
	Description...: get file name from full path
	Parameters....: path - string. Full path
	Return values.: string file name
	Author........: None
	'''
	head, tail = ntpath.split(path)
	return tail or ntpath.basename(head)

def RemovePadding(data, IsPkcs7 = True):
	'''
	Name..........: RemovePadding
	Description...: Remove padding use in cryptography
	Parameters....: data - binary. Input data
	..............: IsPkcs7 - [optional] algorithm remove else use algorithm ISO/IEC 7816-4
	Return values.: binary
	Author........: Zero-0
	'''
	dataLen = len(data)
	if IsPkcs7:
		iPadEnd = struct.unpack('B', data[dataLen-1])[0]
		iPadStart = struct.unpack('B', data[dataLen-iPadEnd])[0]
		if iPadEnd == iPadStart:
			data = data[0:dataLen - iPadStart]
	else:
		i = dataLen - 1
		while i >= (dataLen - 16):
			if data[i] == '\x80':
				data = data[0:i]
				break 
			i -= 1
	return data

def removeCharacters(value, deletechars = '<>:"/\|?*'):
    for c in deletechars:
        value = value.replace(c,'')
    return value;

def Example_1():
	'''
	In ra danh sách các khóa học và tên bài giảng ứng với từng khóa học
	'''
	Login('', '')
	Courses = GetCourses()
	print "Danh sach cac khoa hoc: "
	for course in Courses:
		print course[1]
		Lessions = GetLessions(course[0])
		print "  Cac bai giang: "
		for Lession in Lessions:
			print 4*" " + Lession[1]
		print 20*"="

def Example_2():
	'''
	Download các file video ts từ các khóa học và phân chia chúng vào từng thư mục.
	Để ghép các file ts có thể dùng ffmpeg hoặc các phần mềm tương tự.
	Các file ts này đều là các file có chất lượng HD hoặc full HD tùy theo khóa học.
	'''
	Login('', '')
	Courses = GetCourses()
	for course in Courses:
		pathDirCourse = os.path.join(g_CurrentDir, course[1])
		if not os.path.exists(pathDirCourse): os.mkdir(pathDirCourse)
		Lessions = GetLessions(course[0])
		for Lession in Lessions:
			print Lession[1]
			pathDirLession = os.path.join(pathDirCourse, Lession[1])
			if not os.path.exists(pathDirLession): os.mkdir(pathDirLession)	
			urlVideo = GetUrlMasterPlaylistFromLession(Lession[0])
			urlM3u8HD =  GetM3u8HD(urlVideo)
			listUrlTs = GetPlaylist(urlM3u8HD, True, pathDirLession)
			for urlTs in listUrlTs:
				DownloadTs(urlTs, pathDirLession)
		print 20*"="

def Download():
	print ""
	email = raw_input(' Email: ')
	password = raw_input(' Password: ')
	if (email == "") or (password == ""):
		print ("email hoac password khong co")
		return
	
	if not Login(email, password):
		return

	print 30*"="
	Courses = GetCourses()
	if not Courses: return

	print "Danh sach cac khoa hoc: "
	i = 1
	for course in Courses:
		print "\t %d. %s" % (i, course[1])
		i += 1

	print "\n  Lua chon tai ve cac khoa hoc"
	print "  Vd: 1, 2 hoac 1-5, 7"
	print "  Mac dinh la tai ve het\n"

	rawOption = raw_input('(%s)$: ' % email)

	CoursesDownload = Courses
	if rawOption != "":
		try:
			CoursesDownload = []
			option = rawOption.split(",")
			lenCourses = len(Courses)
			for i in option:
				if i.find("-") != -1:
					c = i.split("-")
					c = map(int, c)
					c[0] -= 1
					if c[0] < 0:
						c[0] = 0
					CoursesDownload += Courses[c[0]:c[1]]
				else:
					index = int(i) - 1
					if index > lenCourses - 1:
						index = lenCourses - 1
					if index < 0:
						index = 0
					CoursesDownload.append(Courses[index])
			CoursesDownload = list(set(CoursesDownload))
		except ValueError:
			print ">>> Lam on nhap so."
			return
	
	try:
		NumOfThread = raw_input('So luong download [5]: ')
		if NumOfThread == "":
			NumOfThread = 5
		NumOfThread = int(NumOfThread)
	except ValueError:
		print ">>> Nhap so"
		return

	IsConvert = False
	Convert = raw_input('Convert Ts to Mp4 [yes]: ')
	if (Convert == "") or (Convert.lower() == "yes") or (Convert.lower() == 'y'):
		IsConvert = True
	listPathDirLessions = []
	DirDownload = os.path.join(g_CurrentDir, "DOWNLOAD")
	if not os.path.exists(DirDownload): os.mkdir(DirDownload)
	print ""
	print 30*"="
	iCourses = 0
	lenCourses = len(CoursesDownload)
	for course in CoursesDownload:
		print course[1]
		pathDirCourse = os.path.join(DirDownload, removeCharacters(course[1], '.<>:"/\|?*\r\n'))
		if not os.path.exists(pathDirCourse): os.mkdir(pathDirCourse)
		pathDirComplete = os.path.join(pathDirCourse, "complete")
		if not os.path.exists(pathDirComplete): os.mkdir(pathDirComplete)
		DirDocuments = os.path.join(pathDirComplete, "Documents")
		if not os.path.exists(DirDocuments): os.mkdir(DirDocuments)
		Lessions = GetLessions(course[0])
		iLessions = 1
		lenLessions = len(Lessions)
		for Lession in Lessions:
			print Lession[1]
			
			pathDirLession = os.path.join(pathDirCourse, removeCharacters(Lession[1], '.<>:"/\|?*\r\n'))
			if not os.path.exists(pathDirLession): os.mkdir(pathDirLession)	
			listPathDirLessions.append(pathDirLession)
			urlVideo, urlDocuments = GetUrlMasterPlaylistFromLession(Lession[0])
			
			if not urlVideo: continue
			threadDownloadDocument = threading.Thread(target = DownloadDocuments, args = (urlDocuments, DirDocuments))
			threadDownloadDocument.setDaemon(True)
			threadDownloadDocument.start()
			
			urlM3u8HD =  GetM3u8HD(urlVideo)
			if not urlM3u8HD: continue

			listUrlTs = GetPlaylist(urlM3u8HD, True, pathDirLession)
			if not listUrlTs: continue
			listOfThread = []
			for i in range(NumOfThread):
				l = listUrlTs[i::NumOfThread] 
				thread = threading.Thread(target = DownloadTss, args = (l, pathDirLession))
				thread.setDaemon(True)
				thread.start()
				listOfThread.append(thread)

			for thread in listOfThread:
				thread.join()
			threadDownloadDocument.join()
			
			percentLessions = iLessions*1.0/lenLessions*100.0
			kernel32.SetConsoleTitleA("Tong: %.2f%% - %s: %.2f%%" % (percentLessions/lenCourses + iCourses*1.0/lenCourses*100.0, course[1], percentLessions))
			iLessions += 1
			time.sleep(5)

		print 40*"="
		iCourses += 1
		kernel32.SetConsoleTitleA("Tong: %.2f%%" % (iCourses*1.0/lenCourses*100.0))
		

	if IsConvert:
		print "Converting ..."
		for i in listPathDirLessions:
			ffmpeg.ConvertInFolder(i)
	
def DownloadKeys():
	print ""
	email = raw_input(' Email: ')
	password = raw_input(' Password: ')
	if (email == "") or (password == ""):
		logger.info("email hoac password khong co")
		return
	if not Login(email, password): return

	print 20*"="
	Courses = GetCourses()
	if not Courses: return
	print "Danh sach cac khoa hoc: "
	i = 1
	for course in Courses:
		print "\t %d. %s" % (i, course[1])
		i += 1

	print "\n  Lua chon tai ve cac key giai ma"
	print "  Vd: 1, 2 hoac 1-5, 7"
	print "  Mac dinh la tai ve het\n"

	rawOption = raw_input('(%s)$: ' % email)

	CoursesDownload = Courses
	if rawOption != "":
		try:
			CoursesDownload = []
			option = rawOption.split(",")
			lenCourses = len(Courses)
			for i in option:
				if i.find("-") != -1:
					c = i.split("-")
					c = map(int, c)
					if c[1] > lenCourses-1:
						c[1] = lenCourses - 1
					if c[0]-1 < 0:
						c[0] = 0
					CoursesDownload += Courses[c[0]:c[1]]
				else:
					index = int(i) - 1
					if index > lenCourses:
						index = lenCourses - 1
					if index < 0:
						index = 0
					CoursesDownload.append(Courses[index])
			CoursesDownload = list(set(CoursesDownload))
		except ValueError:
			print ">>> Lam on nhap so."
			sys.exit(1)
	
	DirDownload = os.path.join(g_CurrentDir, "DOWNLOAD")
	if not os.path.exists(DirDownload): os.mkdir(DirDownload)
	for course in CoursesDownload:
		print course[1]
		pathDirCourse = os.path.join(DirDownload, removeCharacters(course[1]))
		if not os.path.exists(pathDirCourse): os.mkdir(pathDirCourse)
		Lessions = GetLessions(course[0])
		for Lession in Lessions:
			print Lession[1]
			pathDirLession = os.path.join(pathDirCourse, removeCharacters(Lession[1]))
			if not os.path.exists(pathDirLession): os.mkdir(pathDirLession)	
			urlVideo, _ = GetUrlMasterPlaylistFromLession(Lession[0], False)
			urlM3u8HD =  GetM3u8HD(urlVideo)
			listUrlTs = GetPlaylist(urlM3u8HD, True, pathDirLession)
		print 20*"="

def DonwloadLessions():
	print ""
	email = raw_input(' Email: ')
	password = raw_input(' Password: ')
	if (email == "") or (password == ""):
		logger.info("email hoac password khong co")
		return

	if not Login(email, password): return

	print 30*"="
	Courses = GetCourses()
	if not Courses: return

	print " Danh sach cac khoa hoc: "
	i = 1
	for course in Courses:
		print "\t %d. %s" % (i, course[1])
		i += 1

	print "\n Lua chon tai ve 1 khoa hoc"

	rawOption = raw_input(' (%s)$: ' % email)
	try:
		lenCourses = len(Courses)
		index = int(rawOption) - 1
		if index > lenCourses:
			index = lenCourses - 1
		if index < 0:
			index = 0
		course = Courses[index]
	except ValueError:
		print " Lam on nhap SO"
		return

	DirDownload = os.path.join(g_CurrentDir, "DOWNLOAD")
	if not os.path.exists(DirDownload): os.mkdir(DirDownload)
	print 30*"="
	print ""
	print course[1]
	pathDirCourse = os.path.join(DirDownload, removeCharacters(course[1], '.<>:"/\|?*\r\n'))
	if not os.path.exists(pathDirCourse): os.mkdir(pathDirCourse)
	pathDirComplete = os.path.join(pathDirCourse, "complete")
	if not os.path.exists(pathDirComplete): os.mkdir(pathDirComplete)
	DirDocuments = os.path.join(pathDirComplete, "Documents")
	if not os.path.exists(DirDocuments): os.mkdir(DirDocuments)
	Lessions = GetLessions(course[0])
	if not Lessions: return
	print "Danh sach cac bai giang: "
	i = 1
	for Lession in Lessions:
		print "\t %d. %s" % (i, Lession[1])
		i += 1

	print "\n  Lua chon tai ve cac bai giang"
	print "  Vd: 1, 2 hoac 1-5, 7"
	print "  Mac dinh la tai ve het\n"

	rawOption = raw_input(' >> ')

	LessionsDownload = Lessions
	if rawOption != "":
		try:
			LessionsDownload = []
			option = rawOption.split(",")
			lenLessions = len(Lessions)
			for i in option:
				if i.find("-") != -1:
					c = i.split("-")
					c = map(int, c)
					c[0] -= 1
					if c[0] < 0:
						c[0] = 0
					LessionsDownload += Lessions[c[0]:c[1]]
				else:
					index = int(i) - 1
					if index > lenLessions - 1:
						index = lenLessions - 1
					if index < 0:
						index = 0
					LessionsDownload.append(Lessions[index])
			LessionsDownload = list(set(LessionsDownload))
		except ValueError:
			print ">>> Lam on nhap so."
			return

	try:
		NumOfThread = raw_input(' So luong download cung luc [5]: ')
		if NumOfThread == "":
			NumOfThread = 5
		NumOfThread = int(NumOfThread)
	except ValueError:
		print ">>> Nhap so"
		return

	IsConvert = False
	Convert = raw_input(' Convert Ts to Mp4 [yes]: ')
	if (Convert == "") or (Convert.lower() == "yes") or (Convert.lower() == 'y'):
		IsConvert = True

	listPathDirLession = []
	for Lession in LessionsDownload:
		print Lession[1]
		pathDirLession = os.path.join(pathDirCourse, removeCharacters(Lession[1], '.<>:"/\|?*\r\n'))
		if not os.path.exists(pathDirLession): os.mkdir(pathDirLession)
		listPathDirLession.append(pathDirLession)	
		urlVideo, urlDocuments = GetUrlMasterPlaylistFromLession(Lession[0])
	
		if not urlVideo: continue
		threadDownloadDocument = threading.Thread(target = DownloadDocuments, args = (urlDocuments, DirDocuments))
		threadDownloadDocument.setDaemon(True)
		threadDownloadDocument.start()
			
		urlM3u8HD =  GetM3u8HD(urlVideo)
		if not urlM3u8HD: continue

		listUrlTs = GetPlaylist(urlM3u8HD, True, pathDirLession)
		if not listUrlTs: continue
		listOfThread = []
		for i in range(NumOfThread):
			l = listUrlTs[i::NumOfThread] 
			thread = threading.Thread(target = DownloadTss, args = (l, pathDirLession))
			thread.setDaemon(True)
			thread.start()
			listOfThread.append(thread)

		for thread in listOfThread:
			thread.join()
		threadDownloadDocument.join()

		time.sleep(10)
		
	print 40*"="
	
	if IsConvert:
		print "Converting ..."
		for i in listPathDirLession:
			ffmpeg.ConvertInFolder(i)
	
def DecryptFolder():
	pathKey = ""
	Folder = raw_input('Nhap thu muc can giai ma [DOWNLOAD]: ')
	if Folder != "":
		pathKey = raw_input('Nhap duong dan chua key giai ma: ')
		if pathKey == "":
			print "Khong co key"
			sys.exit(1)
	else:
		Folder = os.path.join(g_CurrentDir, "DOWNLOAD")

	for folderName, subfolders, filenames in os.walk(Folder):
		ListFileTs = []
		if folderName.split("\\")[-1] == "Bak": continue
		for filename in filenames:
			if filename.endswith(".key"):
				pathKey = os.path.join(folderName, filename)
			if filename.endswith(".ts"):
				ListFileTs.append(filename)
		try:
			if pathKey != "":
				DirBackup = os.path.join(folderName, 'Bak')
				if not os.path.exists(DirBackup): os.mkdir(DirBackup)
			with open(pathKey, 'rb') as fKey:
				keyData = fKey.read()
				for fileTs in ListFileTs:
					print fileTs
					dest = os.path.join(DirBackup, fileTs)
					src = os.path.join(folderName, fileTs)
					shutil.move(src, dest)
					with open(dest, 'rb') as fTsReader, open(src, 'wb') as fTsWriter:
						fTsWriter.write(Decrypt(fTsReader.read(), keyData))
		except IOError:
			print "Key Not Found - Folder %s" % folderName
		except ValueError as e:
			print "Error {%s} - file: %s" % (e, dest)

def Convert():
	Folder = raw_input('Nhap thu muc can chuyen doi [DOWNLOAD]: ')
	if Folder == "":
		Folder = os.path.join(g_CurrentDir, "DOWNLOAD")
	ffmpeg.ConvertInFolder(Folder)

def menu():
	if getattr(sys, 'frozen', False):
		PATH_LOGO = os.path.join(sys._MEIPASS, 'logo', 'logo.txt')
	else:
		PATH_LOGO = os.path.join(os.getcwd(), 'logo', 'logo.txt')

	with open(PATH_LOGO, 'r') as f:
		for i in f:
			sys.stdout.write(i)
			time.sleep(0.07)

	print ""
	print "\t0. Thoat"
	print "\t1. Tai cac khoa hoc"
	print "\t2. Tai khoa giai ma"
	print "\t3. Giai ma tep trong thu muc"
	print "\t4. Chuyen ts thanh mp4"
	print "\t5. Tai cac bai giang con thieu"
	print ""

def main():

	
	while (True):
		global g_session
		g_session = requests.Session()
		g_session.headers['user-agent'] = g_UserAgent
		os.system('cls')
		menu()
		option = raw_input("\t>> ")
		try:
			option = int(option)
		except ValueError:
			print "\n\t>> Nhap SO <<"
			continue
		if(option == 0):
			return
		elif(option == 1):
			Download()
		elif(option == 2):
			DownloadKeys()
		elif(option == 3):
			DecryptFolder()
		elif(option == 4):
			Convert()
		elif(option == 5):
			DonwloadLessions()
		else:
			print "\n\t>> Khong co lua chon phu hop <<"
		g_session.close()
		tmp = raw_input('\n\tNhan enter de tiep tuc...')

if __name__ == '__main__':
	#os.environ['HTTP_PROXY'] = "http://127.0.0.1:8888"
	#os.environ['HTTPS_PROXY'] = os.environ['HTTP_PROXY']

	try:
		main()
	except KeyboardInterrupt:
		print "CTRL-C break"
