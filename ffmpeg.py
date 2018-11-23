# -*- coding: utf-8 -*-
import sys
import os
import ntpath
import subprocess
import time
import sys
import glob
import re
from natsort import natsort

reload(sys)
sys.setdefaultencoding('utf-8')

if getattr(sys, 'frozen', False):
	FFMPEG_PATH = os.path.join(sys._MEIPASS, 'ffmpeg', 'ffmpeg.exe')
else:
	FFMPEG_PATH = os.path.join(os.getcwd(), 'ffmpeg', 'ffmpeg.exe')

def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

def TsToMp4(Folder, OutPutFileName = ""):
	Files = os.listdir(Folder)
	Files = natsort(Files)
	fullPathFiles = []
	for i in Files:
		path = os.path.join(Folder, i)
		if os.path.isfile(path):
			if i.endswith(".ts"):
				fullPathFiles.append(path)
	if fullPathFiles == []:
		print "Thu muc %s khong co file .ts" % Folder 
		return

	DirComplete = os.path.join(Folder[0:Folder.rfind("\\")], 'complete')
	if not os.path.exists(DirComplete): os.mkdir(DirComplete)
	DirLog = os.path.join(DirComplete, 'log')
	if not os.path.exists(DirLog): os.mkdir(DirLog)
	concatFile = os.path.join(DirComplete, 'concat.txt')
	with open(concatFile, 'w') as f:
		for i in fullPathFiles:
			if os.path.isfile(i):
				f.write("file '%s'\n" % i.replace("'", "'\\''"))

	if OutPutFileName:	
		outputFile = os.path.join(DirComplete, OutPutFileName)
		FileLog = os.path.join(DirLog, OutPutFileName + ".log")
	else:
		outputFile = os.path.join(DirComplete, 'output.mp4')
		FileLog = os.path.join(DirLog, 'output.log')

	args = [FFMPEG_PATH, '-f', 'concat', '-i', concatFile, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', outputFile]

	with open(FileLog, 'w') as f:
		process = subprocess.Popen(args, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
		for line in iter(lambda: process.stdout.read(1), ''):
			sys.stdout.write(line)
			f.write(line.rstrip('\n'))

	os.remove(concatFile)

def ConvertInFolder(Folder):
	for folderName, subfolders, filenames in os.walk(Folder):
		TsToMp4(folderName, folderName.split("\\")[-1] + ".mp4")