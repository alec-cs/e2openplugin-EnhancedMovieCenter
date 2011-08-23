#!/usr/bin/python
# encoding: utf-8
#
# Copyright (C) 2011 by Coolman & Swiss-MAD
#
# In case of reuse of this source code please do not remove this copyright.
#
#	This program is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	This program is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	For more information on the GNU General Public License see:
#	<http://www.gnu.org/licenses/>.
#
import math
import os
from time import time

from Components.config import *
from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest, MultiContentEntryProgress
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import fileExists
from skin import parseColor, parseFont, parseSize
from enigma import eListboxPythonMultiContent, eListbox, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, eServiceReference, eServiceCenter
from timer import TimerEntry

from RecordingsControl import RecordingsControl
from DelayedFunction import DelayedFunction
from EMCTasker import emcDebugOut
from EnhancedMovieCenter import _
from VlcPluginInterface import VlcPluginInterfaceList
from operator import itemgetter
from CutListSupport import CutList
from MetaSupport import MetaList
from EitSupport import EitList


# Media types
audioExt = frozenset([".ac3", ".dts", ".flac", ".m4a", ".mp2", ".mp3", ".ogg", ".wav"])
videoExt = frozenset([".ts", ".avi", ".divx", ".f4v", ".flv", ".img", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".vob"])
playlistExt = frozenset([".m3u"])
dirExt = frozenset([""])
mediaExt = audioExt | videoExt | playlistExt
listExt = mediaExt | dirExt

# Additional file types
tsExt    = frozenset([".ts"])
m2tsExt  = frozenset([".m2ts"])
dvdExt   = frozenset([".iso", ".img", ".ifo"])

# Player types
playerDVB  = tsExt																											# ServiceDVB
playerM2TS = m2tsExt																										# ServiceM2TS
playerDVD  = dvdExt																											# ServiceDVD
playerMP3  = mediaExt - playerDVB - playerM2TS - playerDVD							# ServiceMP3 GStreamer

serviceIdDVB = eServiceReference.idDVB	# eServiceFactoryDVB::id   enum { id = 0x1 }; 
serviceIdDVD = 4369 										# eServiceFactoryDVD::id   enum { id = 0x1111 };
serviceIdMP3 = 4097											# eServiceFactoryMP3::id   enum { id = 0x1001 };
# For later purpose
serviceIdM2TS = 3 											# eServiceFactoryM2TS::id  enum { id = 0x3 };
#TODO
#serviceIdXINE = 4112										# eServiceFactoryXine::id  enum { id = 0x1010 };
#additionalExtensions = "4098:m3u 4098:e2pls 4098:pls"

serviceIdsCuts = frozenset([serviceIdDVB, serviceIdDVD])


#-------------------------------------------------
# func: readBasicCfgFile( file )
#
# Reads the lines of a file in a list. Empty lines
# or lines beginnig with '#' will be ignored.
#-------------------------------------------------
def readBasicCfgFile(file):
	data = []
	f = None
	try:
		f = open(file, "r")
		lines = f.readlines()
		for line in lines:
			line = line.strip()
			if not line:					# no empty lines
				continue
			if line[0:1] == "#":				# no comment lines
				continue
			data.append( line )
	except Exception, e:
		emcDebugOut("[EMC] Exception in readBasicCfgFile: " + str(e))
	finally:
		if f is not None:
			f.close()
	return data

def getMovieName(filename, service=None, date=""):
	moviestring = ""
	metastring = ""
	eitstring = ""
	cutnr = ""
	length = 0
	sortmoviestring = ""
	
	# Remove extension
	filename, ext = os.path.splitext(filename)
	
	# Get cut number
	if filename[-4:-3] == "_" and filename[-3:].isdigit():
		cutnr = filename[-3:]
		# Remove cut number
		filename = filename[:-4]
	
	# Replace underscores with spaces
	filename = filename.replace("_"," ")
	
	# Derived from RecordTimer
	# This is everywhere so test it first
	if filename[0:8].isdigit():
		if filename[9:13].isdigit() and not filename[8:9].isdigit():
			# Default: filename = YYYYMMDD TIME - service_name
			date = filename[0:8] + filename[9:13]		# "YYYYMMDD TIME - " -> "YYYYMMDDTIME"
			moviestring = filename[16:]							# skips "YYYYMMDD TIME - "
			
			# Standard: filename = YYYYMMDD TIME - service_name - name
			# Long Composition: filename = YYYYMMDD TIME - service_name - name - description
			# Standard: filename = YYYYMMDD TIME - service_name - name
			# Skip service_name, extract name
			moviestring = str.split(moviestring, " - ")
			moviestring = moviestring[1:]								# To remove the description use [1:len(moviestring)-1] But the description must be there
			moviestring = ' - '.join(str(n) for n in moviestring)
				
		elif filename[8:11] == " - ":
			# Short Composition: filename = YYYYMMDD - name
			date = filename[0:8] + "3333"						# "YYYYMMDD" + DUMMY_TIME
			moviestring = filename[11:]							# skips "YYYYMMDD - "
	
	if not moviestring:
		# Calculate date string for sorting
		# YYYYMMDD HHMM from DD.MM.YYYY HH:MM
		date = date[6:10] + date[3:5] + date[0:2] + date[11:13] + date[14:]
		moviestring = filename[:]
	
	if config.EMC.movie_metaload.value and service:
		# read title from META
		meta = MetaList(service)
		metastring = meta and meta.getMetaName()
		# Improve performance and avoid calculation of movie length
		length = meta and meta.getMetaLength()
		# Maybe read also the rectime
		
	if not metastring and config.EMC.movie_eitload.value and service:
			# read title from EIT
			eit = EitList(service)
			eitstring = eit and eit.getEitName()
			if not length:
				length = eit and eit.getEitLengthInSeconds()
				#TEST EIT len
				print "EMC eit length: " + str(moviestring) + " " + str(length)
				# Maybe read also the start date / time
	
	moviestring = metastring or eitstring or moviestring
	
	# Very bad but there can be both encodings
	# E2 recordings are always in utf8
	# User files can be in cp1252
	# Is there no other way?
	try:
		moviestring.decode('utf-8')
	except UnicodeDecodeError:
		moviestring = moviestring and moviestring.decode("cp1252").encode("utf-8")
	
	# Create sortkeys
	sortmoviestring = moviestring.lower()
	sortkeyalpha = sortmoviestring + date + cutnr
	sortkeydate = date + sortmoviestring + str( 999 - int(cutnr or 0) )
	sortingkeys = (sortkeyalpha, sortkeydate)
	
	if config.EMC.movie_show_cutnr.value:
		moviestring += " "+cutnr
	
	if config.EMC.movie_show_format.value:
		moviestring += " "+ext[1:]
	
	return moviestring, length, sortingkeys

class MovieCenter(GUIComponent, VlcPluginInterfaceList):
	instance = None
	
	def __init__(self):
		MovieCenter.instance = self
		self.list = []
		GUIComponent.__init__(self)
		VlcPluginInterfaceList.__init__(self)
		self.loadPath = config.EMC.movie_homepath.value
		if not self.loadPath.endswith("/"): self.loadPath += "/"
		self.serviceHandler = eServiceCenter.getInstance()
		self.returnSort = None
		self.CoolFont = parseFont("Regular;20", ((1,1),(1,1)))
		self.CoolSelectFont = parseFont("Regular;20", ((1,1),(1,1)))
		self.CoolDateFont = parseFont("Regular;20", ((1,1),(1,1)))
		
		self.CoolMoviePos = 100
		self.CoolMovieSize = 490
		self.CoolFolderSize = 550
		self.CoolDatePos = -1
		self.CoolDateWidth = 110
		self.CoolDateColor = 0
		self.CoolProgressPos = -1
		self.CoolBarPos = -1
		self.CoolBarHPos = 8
		
		self.CoolBarSize = parseSize("55,10", ((1,1),(1,1)))
		self.CoolBarSizeSa = parseSize("55,10", ((1,1),(1,1)))
		
		self.DateColor = 0xFFFFFF
		self.DefaultColor = 0xFFFFFF
		self.BackColor = None
		self.BackColorSel = 0x000000
		self.UnwatchedColor = 0xFFFFFF
		self.WatchingColor = 0x3486F4
		self.FinishedColor = 0x46D93A
		self.RecordingColor = 0x9F1313
		#IDEA self.CutColor
		
		self.l = eListboxPythonMultiContent()
		self.l.setFont(0, gFont("Regular", 22))
		self.l.setFont(1, self.CoolFont)
		self.l.setFont(2, gFont("Regular", 20))
		self.l.setFont(3, self.CoolSelectFont)
		self.l.setFont(4, self.CoolDateFont)
		self.l.setBuildFunc(self.buildMovieCenterEntry)
		self.l.setItemHeight(28)
		self.currentSelectionCount = 0		
		
		self.alphaSort = config.EMC.CoolStartAZ.value
		self.selectionList = None
		self.recControl = RecordingsControl(self.recStateChange)
		self.highlightsMov = []
		self.highlightsDel = []
		
		self.backPic         = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/back.png')
		self.dirPic          = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dir.png')
		self.movie_default   = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_default.png')
		self.movie_unwatched = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_unwatched.png')
		self.movie_watching  = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_watching.png')
		self.movie_finished  = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_finished.png')
		self.movie_rec       = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_rec.png')
		self.movie_recrem    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_recrem.png')
		#IDEA self.movie_cut = LoadPixmap
		self.mp3Pic          = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/music.png')
		self.dvd_default     = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_default.png')
		self.dvd_watching    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_watching.png')
		self.dvd_finished    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_finished.png')
		self.playlistPic     = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/playlist.png')
		self.vlcPic          = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/vlc.png')
		self.vlcdPic         = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/vlcdir.png')
		self.link            = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/link.png')
		self.virtualPic      = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/virtual.png')
		self.onSelectionChanged = []
		
		self.hideitemlist = []
		if config.EMC.cfghide_enable.value:
			self.hideitemlist = readBasicCfgFile("/etc/enigma2/emc-hide.cfg")
		
		self.nostructscan = []
		if config.EMC.cfgnoscan_enable.value:
			self.nostructscan = readBasicCfgFile("/etc/enigma2/emc-noscan.cfg")
		
		# Initially load the movielist
		# So it must not be done when the user it opens the first time
		#MAYBE this should be configurable
		emcDebugOut("[EMC_MC] test delayed reload ")
		DelayedFunction(10000, self.reload, self.loadPath)

	def applySkin(self, desktop, parent):
		attribs = []
		if self.skinAttributes is not None:
			for (attrib, value) in self.skinAttributes:
				if attrib == "CoolFont":
					self.CoolFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(1, self.CoolFont)
				elif attrib == "CoolSelectFont":
					self.CoolSelectFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(3, self.CoolSelectFont)
				elif attrib == "CoolDateFont":
					self.CoolDateFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(4, self.CoolDateFont)
				elif attrib == "CoolDirPos":
					pass
				
				elif attrib == "CoolMoviePos":
					self.CoolMoviePos = int(value)
				elif attrib == "CoolMovieSize":
					self.CoolMovieSize = int(value)
				elif attrib == "CoolFolderSize":
					self.CoolFolderSize = int(value)
				elif attrib == "CoolDatePos":
					self.CoolDatePos = int(value)
				elif attrib == "CoolDateWidth":
					self.CoolDateWidth = int(value)
				elif attrib == "CoolDateColor":
					self.CoolDateColor = int(value)
				elif attrib == "CoolTimePos":
					pass
				
				elif attrib == "CoolProgressPos":
					self.CoolProgressPos = int(value)
				elif attrib == "CoolBarPos":
					self.CoolBarPos = int(value)
				elif attrib == "CoolBarHPos":
					self.CoolBarHPos = int(value)
				elif attrib == "CoolBarSize":
					self.CoolBarSize = parseSize(value, ((1,1),(1,1)))
				elif attrib == "CoolBarSizeSa":
					self.CoolBarSizeSa = parseSize(value, ((1,1),(1,1)))
				elif attrib == "DefaultColor":
					self.DefaultColor = parseColor(value).argb()
				elif attrib == "BackColor":
					self.BackColor = parseColor(value).argb()
				elif attrib == "BackColorSel":
					self.BackColorSel = parseColor(value).argb()
				elif attrib == "UnwatchedColor":
					self.UnwatchedColor = parseColor(value).argb()
				elif attrib == "WatchingColor":
					self.WatchingColor = parseColor(value).argb()
				elif attrib == "FinishedColor":
					self.FinishedColor = parseColor(value).argb()
				elif attrib == "RecordingColor":
					self.RecordingColor = parseColor(value).argb()
				else:
					attribs.append((attrib, value))
		self.skinAttributes = attribs
		return GUIComponent.applySkin(self, desktop, parent)

	def selectionChanged(self):
		for f in self.onSelectionChanged:
			try:
				f()
			except Exception, e:
				emcDebugOut("[MC] External observer exception: \n" + str(e))

	def setAlphaSort(self, trueOrFalse):
		self.returnSort == None
		self.alphaSort = trueOrFalse
		self.list = self.doListSort(self.list)
		self.l.setList( self.list )

	def getAlphaSort(self):
		return self.alphaSort

	def doListSort(self, sortlist):
		# If [7] = ext = None then it is a directory or special folder entry
		#TODO should be [2] = date = None - but vlc part has to be changed
		tmplist = [i for i in sortlist if i[7] is None]
		
		# Extract list items to be sorted
		sortlist = sortlist[len(tmplist):]
		
		# Sort list
		# Using itemgetter is slightly faster but not as flexible
		# Then the list has to be flat, no sub tuples were allowed (key=itemgetter(x))
		if self.alphaSort:
			sortlist.sort( key=lambda x: (x[1][0]), reverse=config.EMC.moviecenter_reversed.value )
		else:
			sortlist.sort( key=lambda x: (x[1][1]), reverse=not config.EMC.moviecenter_reversed.value )
		
		# Combine lists
		return tmplist + sortlist

	def recStateChange(self, timer):
		if timer:
			path = os.path.dirname(timer.Filename)
			if path == self.loadPath[:-1]:
			#if timer and timer.dirname == self.loadPath:
				# EMC shows the directory which contains the recording
				if timer.state == TimerEntry.StateRunning:
					if not self.list:
						# Empty list it will be better to reload it complete
						# Maybe EMC was never started before
						emcDebugOut("[MC] Timer started - full reload")
						DelayedFunction(3000, self.reload, self.loadPath)
					else:
						# We have to add the new recording
						emcDebugOut("[MC] Timer started - add recording")
						# Timer filname is without extension
						filename = timer.Filename + ".ts"
						DelayedFunction(3000, self.reload, filename)
				elif timer.state == TimerEntry.StateEnded:
					#MAYBE Just refresh the ended record
					# But it is fast enough
					emcDebugOut("[MC] Timer ended")
					DelayedFunction(3000, self.invalidateList)
# 			#WORKAROUND Player is running during a record ends
# 			# We should find a more flexible universal solution
# 			from MovieSelection import gMS
# 			if gMS and gMS.playerInstance is not None:
# 				DelayedFunction(3000, self.updatePlayer)
# 
# 	def updatePlayer(self):
# 		from MovieSelection import gMS
# 		if gMS and gMS.playerInstance is not None:
# 			gMS.playerInstance.updateCuesheet(gMS)

	def getProgress(self, service, length=0, last=0, forceRecalc=False, cuts=None):
		# All calculations are done in seconds
		# The progress of a recording isn't correct, because we only get the actual length not the final
		cuts = None
		progress = 0
		updlen = length
		if last <= 0:
			# Get last position from cut file
			if cuts is None:
				cuts = CutList( service )
			last = cuts.getCutListLast()
		# Check for valid position
		if last > 0 or forceRecalc:
			# Valid position
			# Recalc the movie length to calculate the progress status
			if length <= 0: 
				if service:
					length = self.getLengthFromServiceHandler(service)
				if length <= 0: 
					if cuts is None:
						cuts = CutList( service )
					length = cuts.getCutListLength()
					if length <= 0: 
						# Set default file length if is not calculateable
						# 90 minutes = 90 * 60
						length = 5400
						# We only update the entry if we do not use the default value
						updlen = 0
						#emcDebugOut("[MC] getProgress No length: " + str(service.getPath()))
					else:
						updlen = length
				else:
					updlen = length
				if updlen:
					self.updateLength(service, updlen)
			if length:
				progress = self.calculateProgress(last, length)
			else:
				# This should never happen, we always have our default length
				progress = 100
				#emcDebugOut("[MC] getProgress(): Last without any length")
		else:
			# No position implies progress is zero
			progress = 0
		return progress

	def getRecordProgress(self, service, path):
		# The progress of all recordings is updated
		# - on show dialog
		# - on reload list / change directory / movie home
		# The progress of one recording is updated
		# - if it will be highlighted the list
		# Note: There is no auto update mechanism of the recording progress
		begin, end = self.recControl.getRecordingTimes(path)
		last = time() - begin
		length = end - begin
		return self.calculateProgress(last, length)

	def calculateProgress(self, last, length):
		progress = 0
		if length:
			# Adjust the watched movie length (98% of movie length) 
			# else we will never see the 100%
			adjlength = float(length) / 100.0 * 98.0
			# Calculate progress and round up
			progress = int( math.ceil ( float(last) / float(adjlength) * 100.0 ) )
			# Normalize progress
			if progress < 0: progress = 0
			elif progress > 100: progress = 100
		return progress

	def updateLength(self, service, length):
		# Update entry in list... so next time we don't need to recalc
		idx = self.getIndexOfService(service)
		if idx >= 0:
			x = self.list[idx]
			if x[6] != length:
				l = list(x)
				l[6] = length
				self.list[idx] = tuple(l)

	def buildMovieCenterEntry(self, service, sortkeys, date, moviestring, filename, selnum, length, ext):
		offset = 0
		progressWidth = 55
		globalHeight = 40
		progress = 0
		pixmap = None
		color = None
		colordate = None
		
		res = [ None ]
		append = res.append
		
		path = self.loadPath + filename
		
		#TODO this is the third or more islink/isfile check we should store it somewhere
		isLink = os.path.islink(path)
		
		usedFont = int(config.EMC.skin_able.value)
		
		# Directory and vlc entries
		if ext is None:
			if filename=="VLC servers":
				pixmap = self.vlcdPic
				date = _("< VLC >")
			elif filename=="Latest Recordings":
				pixmap = self.virtualPic
				date = _("< Latest >")
			elif filename=="..": 
				pixmap = self.backPic
			else:
				pixmap = self.dirPic
				date = _("Directory")
				
			append(MultiContentEntryPixmapAlphaTest(pos=(5,2), size=(24,24), png=pixmap, **{}))
			if isLink:
				date = _("< Link >")
				append(MultiContentEntryPixmapAlphaTest(pos=(7,13), size=(9,10), png=self.link, **{}))
			# Directory left side
			append(MultiContentEntryText(pos=(30, 0), size=(self.CoolFolderSize, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=moviestring))
			# Directory right side
			append(MultiContentEntryText(pos=(self.l.getItemSize().width() - self.CoolDateWidth, 0), size=(self.CoolDateWidth, globalHeight), font=2, flags=RT_HALIGN_CENTER, text=date))
				
		else:
			if date == "VLCs":
				date = "VLC"
				pixmap = self.vlcPic
				color = self.DefaultColor
				if self.CoolDateColor == 0:
					colordate = self.DateColor
				else:
					colordate = color
			
			elif self.recControl.isRecording(path):
				date = "-- REC --"
				pixmap = self.movie_rec
				color = self.RecordingColor
				colordate = self.RecordingColor
				# Recordings status shows always the progress of the recording, 
				# Never the progress of the cut list marker to avoid misunderstandings
				progress = service and self.getRecordProgress(service, path) or 0
			
			elif config.EMC.remote_recordings.value and self.recControl.isRemoteRecording(path):
				date = "-- rec --"
				pixmap = self.movie_recrem
				color = self.RecordingColor
				colordate = self.RecordingColor
			
			#IDEA elif config.EMC.check_movie_cutting.value:
			elif self.recControl.isCutting(path):
				date = "-- CUT --"
				pixmap = self.movie_rec
				color = self.RecordingColor
				colordate = self.RecordingColor
			
			else:
				progress = service and self.getProgress(service, length) or 0
				
				# Progress State
				movieUnwatched = config.EMC.movie_mark.value and	progress < int(config.EMC.movie_watching_percent.value)
				movieWatching  = config.EMC.movie_mark.value and	progress >= int(config.EMC.movie_watching_percent.value) and progress < int(config.EMC.movie_finished_percent.value)
				movieFinished  = config.EMC.movie_mark.value and	progress >= int(config.EMC.movie_finished_percent.value)
				
				# Icon
				global audioExt, dvdExt, videoExt, playlistExt
				# video
				if ext in videoExt:
					if movieUnwatched:
						pixmap = self.movie_unwatched
					elif movieWatching:
						pixmap = self.movie_watching
					elif movieFinished:
						pixmap = self.movie_finished
					else:
						pixmap = self.movie_default
				# audio
				elif ext in audioExt:
					pixmap = self.mp3Pic
				# dvd iso or structure
				elif ext in dvdExt: # or ext == "":  #Workaround for DVD folder
					if movieWatching:
						pixmap = self.dvd_watching
					elif movieFinished:
						pixmap = self.dvd_finished
					else:
						pixmap = self.dvd_default
				# playlists
				elif ext in playlistExt:
					pixmap = self.playlistPic
				# all others
				else:
					pixmap = self.movie_default
				
				# Color
				if movieUnwatched:
					color = self.UnwatchedColor
				elif movieWatching:
					color = self.WatchingColor
				elif movieFinished:
					color = self.FinishedColor
				else:
					color = self.DefaultColor
				
			if self.CoolDateColor == 0:
				colordate = self.DateColor
			else:
				colordate = color
		
			selnumtxt = None
			if selnum == 9999: selnumtxt = "-->"
			elif selnum == 9998: selnumtxt = "X"
			elif selnum > 0: selnumtxt = "%02d" % selnum
			if service in self.highlightsMov: selnumtxt = "-->"
			elif service in self.highlightsDel: selnumtxt = "X"
		
			if config.EMC.movie_icons.value and selnumtxt is None:
				append(MultiContentEntryPixmapAlphaTest(pos=(5,2), size=(24,24), png=pixmap, **{}))
				if isLink:
					append(MultiContentEntryPixmapAlphaTest(pos=(7,13), size=(9,10), png=self.link, **{}))
				offset = 35
			if selnumtxt is not None:
				append(MultiContentEntryText(pos=(5, 0), size=(26, globalHeight), font=3, flags=RT_HALIGN_LEFT, text=selnumtxt))
				offset += 35
			
			if config.EMC.skin_able.value:
				if self.CoolBarPos != -1:
					append(MultiContentEntryProgress(pos=(self.CoolBarPos, self.CoolBarHPos -2), size = (self.CoolBarSizeSa.width(), self.CoolBarSizeSa.height()), percent = progress, borderWidth = 1, foreColor = color, backColor = color))
				if self.CoolProgressPos != -1:
					append(MultiContentEntryText(pos=(self.CoolProgressPos, 0), size=(progressWidth, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text="%d%%" % (progress)))
				if self.CoolDatePos != -1:
					append(MultiContentEntryText(pos=(self.CoolDatePos, 2), size=(self.CoolDateWidth, globalHeight), font=4, text=date, color = colordate, color_sel = colordate, flags=RT_HALIGN_CENTER))
					
				append(MultiContentEntryText(pos=(self.CoolMoviePos, 0), size=(self.CoolMovieSize, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=moviestring))
				return res
			
			if config.EMC.movie_progress.value == "PB":
				append(MultiContentEntryProgress(pos=(offset, self.CoolBarHPos), size = (self.CoolBarSize.width(), self.CoolBarSize.height()), percent = progress, borderWidth = 1, backColorSelected = None, foreColor = color, backColor = color))
				offset += self.CoolBarSize.width() + 10
			elif config.EMC.movie_progress.value == "P":
				append(MultiContentEntryText(pos=(offset, 0), size=(progressWidth, globalHeight), font=usedFont, flags=RT_HALIGN_CENTER, text="%d%%" % (progress), color = color, color_sel = color, backcolor = self.BackColor, backcolor_sel = self.BackColorSel))
				offset += progressWidth + 5
			
			if config.EMC.movie_date.value:
				append(MultiContentEntryText(pos=(self.l.getItemSize().width() - self.CoolDateWidth, 0), size=(self.CoolDateWidth, globalHeight), font=4, color = colordate, color_sel = colordate, backcolor = self.BackColor, backcolor_sel = self.BackColorSel, flags=RT_HALIGN_CENTER, text=date))
			append(MultiContentEntryText(pos=(offset, 0), size=(self.l.getItemSize().width() - offset - self.CoolDateWidth -5, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=moviestring))
		
		del append
		return res

	def getCurrent(self):
		l = self.l.getCurrentSelection()
		return l and l[0]

	def getCurrentIndex(self):
		return self.instance.getCurrentIndex()

	def getCurrentEvent(self):
		l = self.l.getCurrentSelection()
		if l and l[0]:
			info = self.serviceHandler.info(l[0])
			return info and info.getEvent(l[0])

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setWrapAround(True)
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)

	def removeService(self, service):
		if service:
			for l in self.list[:]:
				if l[0] == service:
					self.list.remove(l)
			self.l.setList(self.list)

	def serviceBusy(self, service):
		return service in self.highlightsMov or service in self.highlightsDel

	def serviceMoving(self, service):
		return service and service in self.highlightsMov

	def serviceDeleting(self, service):
		return service and service in self.highlightsDel

	def highlightService(self, enable, mode, service):
		if enable:
			if mode == "move":
				self.highlightsMov.append(service)
				self.toggleSelection(service, overrideNum=9999)
			elif mode == "del":
				self.highlightsDel.append(service)
				self.toggleSelection(service, overrideNum=9998)
		else:
			if mode == "move":
				self.highlightsMov.remove(service)
			elif mode == "del":
				self.highlightsDel.remove(service)

	def __len__(self):
		return len(self.list)

	def makeSelectionList(self):
		selList = []
		if self.currentSelectionCount == 0:
			# if no selections made, select the current cursor position
			single = self.l.getCurrentSelection()
			if single:
				selList.append(single[0])
		else:
			selList = self.selectionList
		return selList

	def resetSelection(self):
		self.selectionList = None
		self.currentSelectionCount = 0

	def unselectService(self, service):
		if service:
			if self.selectionList:
				if service in self.selectionList:
					# Service is in selection - unselect it
					self.toggleSelection(service)
				else:
					self.invalidateService(service)
			else:
				self.invalidateService(service)

	def toggleSelection(self, service=None, index=-1, overrideNum=None):
		x = None
		if service is None:
			if index == -1:
				if self.l.getCurrentSelection() is None: return
				index = self.getCurrentIndex()
			x = self.list[index]
		else:
			index = 0
			for e in self.list:
				if e[0] == service:
					x = e
					break
				index += 1
		if x is None: return
		
		# We have x=service, index, overrideNum
		if self.indexIsDirectory(index): return
		if self.selectionList == None:
			self.selectionList = []
		newselnum = x[5]	# init with old selection number
		if overrideNum == None:
			if self.serviceBusy(x[0]): return	# no toggle if file being operated on
			# basic selection toggle
			if newselnum == 0:
				# was not selected
				self.currentSelectionCount += 1
				newselnum = self.currentSelectionCount
				self.selectionList.append(x[0]) # append service
			else:
				# was selected, reset selection number and decrease all that had been selected after this
				newselnum = 0
				self.currentSelectionCount -= 1
				count = 0
				if x is not None:
					self.selectionList.remove(x[0]) # remove service
				for i in self.list:
					if i[5] > x[5]:
						l = list(i)
						l[5] = i[5]-1
						self.list[count] = tuple(l)
						self.l.invalidateEntry(count) # force redraw
					count += 1
		else:
			newselnum = overrideNum * (newselnum == 0)
		l = list(x)
		l[5] = newselnum
		self.list[index] = tuple(l)
		self.l.invalidateEntry(index) # force redraw of the modified item

	def getLengthFromServiceHandler(self, service):
		# Get the movie length in seconds
		if service:
			info = self.serviceHandler.info(service)
			if info:
				return info.getLength(service)
			else:
				return 0
		else:
			return 0

	def getFileNameOfService(self, service):
		if service:
			for entry in self.list:
				if entry[0] == service:
					return entry[4]
		return ""

	def getLengthOfService(self, service):
		if service:
			for entry in self.list:
				if entry[0] == service:
					return entry[6]
		return 0

	def getIndexOfService(self, service):
		if service:
			idx = 0
			for entry in self.list:
				if entry[0] == service:
					return idx
				idx += 1
		return -1
	
	def getServiceOfIndex(self, index):
		return self.list[index] and self.list[index][0]
	
	def invalidateCurrent(self):
		self.l.invalidateEntry(self.getCurrentIndex())

	def invalidateService(self, service):
		idx = self.getIndexOfService(service)
		if idx < 0: return
		self.l.invalidateEntry( idx ) # force redraw of the item

	def detectDVDStructure(self, loadPath):
		if not os.path.isdir(loadPath):
			return None
		elif config.EMC.noscan_linked.value and os.path.islink(loadPath):
			return None
		elif fileExists(loadPath + "/VIDEO_TS.IFO"):
			return loadPath + "/VIDEO_TS.IFO"
		elif fileExists(loadPath + "/VIDEO_TS/VIDEO_TS.IFO"):
			return loadPath + "/VIDEO_TS/VIDEO_TS.IFO"
		return None
	
	def createLatestRecordingsList(self):
		global listExt, mediaExt
		# Make loadPath more flexible
		#MAYBE: What about using current folder for latest recording lookup?
		loadPath = config.EMC.movie_homepath.value
		if not loadPath.endswith("/"): loadPath += "/"
		emcDebugOut("[MC] reloadLatestRecordings, loadPath: " + loadPath)
		trashcan = False
		filelist = []
		append = filelist.append
		pathname, ext, date = "", "", ""
		# Improve performance and avoid dots
		movie_trashpath = config.EMC.movie_trashpath.value
		
		# walk through entire tree below movie home. Might take a bit long und huge disks... 
		# think about doing a manual recursive search via listdir() and stop at 2nd level, 
		# but include folders used in timers, auto timers and bookmarks
		for root, dirs, files in os.walk(loadPath):
			
			#MAYBE we should call here createDirList and reuse the directory and file handling
			
			for p in files:
				
				# This will increase the function execution time massively
				ext = os.path.splitext(p)[1].lower()
				if ext not in listExt:
					continue
				
				# Filter trashcan
				if p.find(movie_trashpath)>-1:
					continue
				
				#MAYBE: Take a look into dirs  and dvdstruct folder -> Missing
				
				pathname = os.path.join(root, p)
				if os.path.isfile(pathname):
					# Media extension check is done implizit - avoid retest ( if ext in mediaExt: )
					date = strftime( "%Y%m%d %H%M", localtime(os.path.getmtime(pathname)) )
					append( (pathname, p, ext, date) )
		
		filelist.sort(key=lambda x: x[3], reverse=True)
		filelist = filelist[:12]
		filelist = [(i[0], i[1], i[2], strftime( "%d.%m.%Y %H:%M", localtime(os.path.getmtime(i[0])))) for i in filelist]
		
		del append
		
		# Return the 12 latest recordings
		return filelist

	def createDirList(self, loadPath):
		global listExt, mediaExt
		dirlist, subdirlist, filelist = [], [], []
		dvdStruct = None
		pathname, ext, date = "", "", ""
		check_dvdstruct = config.EMC.check_dvdstruct.value and loadPath not in self.nostructscan
		# Improve performance and avoid dots
		movie_trashpath = config.EMC.movie_trashpath.value
		dappend = subdirlist.append
		fappend = filelist.append
		getmtime = os.path.getmtime
		splitext = os.path.splitext
		
		# Get directory listing
		# only need to deal with spaces when executing in shell
		# Takes 0.1-1s 
		dirlist = os.listdir(loadPath)
		
		# Maybe someone wants to test and compare performance later glob vs listdir
		#import glob #for f in glob.glob("*.f"):
		
		# add sub directories to the list
		if dirlist:
			
			# Takes 0.5s
			for p in dirlist:
				
				# This will increase the function execution time massively
				ext = splitext(p)[1].lower()
				if ext not in listExt:
					continue
				
				if p in self.hideitemlist or (p[0:1] == "." and ".*" in self.hideitemlist):
					continue
				
				pathname = os.path.join(loadPath, p)
				
				if os.path.isfile(pathname):
					# Media file found
					# Check is done implizit with in listDir, avoid retesting ( if ext in mediaExt )
					#MAYBE Check if file exists, to hide dead links ( if os.path.exists(pathname) )
					date = strftime( "%d.%m.%Y %H:%M", localtime(getmtime(pathname)) )
					fappend( (pathname, p, ext, date) )
				
				elif os.path.isdir(pathname):
					if check_dvdstruct:
						dvdStruct = self.detectDVDStructure(pathname)
						if dvdStruct:
							# DVD Structure found
							pathname = os.path.dirname(dvdStruct)
							ext = splitext(dvdStruct)[1].lower()
							date = strftime( "%d.%m.%Y %H:%M", localtime(getmtime(dvdStruct)) )
							fappend( (pathname, p, ext, date) )
							continue
					
					# Folder found
					if pathname != movie_trashpath:
						#TODO Maybe we should use ext = "DIR"
						#BUT sorting depends on ext is none
						#TODO Use date additionally
						dappend( (pathname, p) )
		
		del dappend
		del fappend
		del splitext
		del getmtime
		return subdirlist, filelist

	def createCustomList(self, loadPath, trashcan=True, extend=True):
		customlist = []
		append = customlist.append
		#TODO
		#use ext = "EMC"
		#use date = time() as string ?
		
		if loadPath != "/" and loadPath[:-1] != config.EMC.movie_pathlimit.value:
			append( ("..", "..") )
		
		if extend:
			# Insert these entries always at last
			if loadPath[:-1] == config.EMC.movie_homepath.value:
				if trashcan and not config.EMC.movie_trashcan_hide.value:
					append( (config.EMC.movie_trashpath.value, os.path.basename(config.EMC.movie_trashpath.value)) )
				
				if config.EMC.latest_recordings.value:
					append( (loadPath+"Latest Recordings/", "Latest Recordings") )
				
				if config.EMC.vlc.value and os.path.exists("/usr/lib/enigma2/python/Plugins/Extensions/VlcPlayer"):
					append( (loadPath+"VLC servers/", "VLC servers") )
				
				if config.EMC.bookmarks_e2.value:
					bookmarks = config.movielist and config.movielist.videodirs and config.movielist.videodirs.value[:]
					if bookmarks:
						for bookmark in bookmarks:
							#TODO ext = bm
							append( (bookmark, "E2 "+os.path.basename(bookmark[:-1])) )
		
		del append
		return customlist

	def createFileInfo(self, pathname):
		# Create info for new record
		#filelist = []
		p = os.path.basename(pathname)
		ext = os.path.splitext(p)[1].lower()
		date = strftime( "%d.%m.%Y %H:%M", localtime(os.path.getmtime(pathname)) )
		#filelist.append( (pathname, p, ext, date) )
		#return filelist
		#TEST
		return [ (pathname, p, ext, date) ]

	def reload(self, loadPath):
		emcDebugOut("[MC] LOAD PATH:\n" + str(loadPath))
		customlist, subdirlist, filelist, tmplist = [], [], [], []
		append = tmplist.append
		service = None
		moviestring, date = "", ""
		length = 0
		resetlist = True
		dosort = True
		sortingkeys = []
		alphaSort = None
		
		if config.EMC.remote_recordings.value:
			# get a list of current remote recordings
			self.recControl.recFilesRead()
		
		# Create listings
		if os.path.isdir(loadPath):
			# Found directory
			if not loadPath.endswith("/"): loadPath += "/"
			
			# Read subdirectories and filenames
			# Takes 0.6 - 2s
			subdirlist, filelist = self.createDirList(loadPath)
			
			customlist = self.createCustomList(loadPath) or []
		
		elif os.path.isfile(loadPath):
			# Found file
			resetlist = False
			filelist = self.createFileInfo(loadPath)
		
		else:
			# Found virtual directory
			
			if loadPath.endswith("VLC servers/"):
				emcDebugOut("[EMC] VLC Server")
				subdirlist = self.createVlcServerList(loadPath)
				customlist = self.createCustomList(loadPath, extend=False) or []
			
			elif loadPath.find("VLC servers/")>-1:
				emcDebugOut("[EMC] VLC Files")
				subdirlist, filelist = self.createVlcFileList(loadPath)
			
			elif loadPath.endswith("Latest Recordings/"):
				emcDebugOut("[EMC] Latest Recordings")
				dosort = False
				filelist = self.createLatestRecordingsList()
				customlist = self.createCustomList(loadPath, extend=False) or []
				alphaSort = False
			
			else:
				raise Exception(_("[EMC] Reload error"))
		
		# Add custom entries and sub directories to the list
		customlist += subdirlist
		if customlist is not None:
			for path, filename in customlist:
				service = self.getPlayerService(path, filename)
				#TODO
				#moviestring, sortingkeys = getDirectoryName(filename, service, date)
				append((service, (None, None), None, filename, filename, 0, 0, None))
		
		# Improve performance and avoid dots
		movie_hide_mov = config.EMC.movie_hide_mov.value
		movie_hide_del = config.EMC.movie_hide_del.value
		
		# Add file entries to the list
		if filelist is not None:
			for path, filename, ext, date in filelist:
				service = self.getPlayerService(path, filename, ext)
				
				# Check config settings
				if service:
					if (movie_hide_mov and self.serviceMoving(service)) \
						or (movie_hide_del and self.serviceDeleting(service)):
						continue
				
				# Filename handling
				# Takes 0.5s
				# Takes 5s with reading from META
				moviestring, length, sortingkeys = getMovieName(filename, service, date)
				
				# Correct date string to get only DD.MM.YYYY
				#IDEA: What about displaying the time optionally
				date = date[0:10]
				
				append((service, sortingkeys, date, moviestring, filename, 0, length, ext))
		
		# If we are here, there is no way back
		self.currentSelectionCount = 0
		self.selectionList = None
		self.loadPath = loadPath
		
		if self.returnSort:
			# Restore sorting mode
			self.alphaSort = self.returnSort
			self.returnSort =None
		
		if alphaSort:
			# Backup the actual sorting mode
			self.returnSort = self.alphaSort
			# Set new sorting mode
			self.alphaSort = alphaSort
		
		if resetlist:
			self.list = []
		else:
			tmplist = self.list + tmplist
		
		if dosort:
			# Do list sort
			self.list = self.doListSort( tmplist )
		else:
			self.list = tmplist
			
		# Assign list to listbox
		self.l.setList( self.list )
		
		del append

	def invalidateList(self):
		# Just invalidate the whole list to force rebuild the entries 
		# Update the progress of all entries
		self.l.invalidate()

	def refreshRecordings(self):
		# Just for updating the progress of the recordings
		#IDEA Extend the list and mark the recordings 
		# so we don't have to go through the whole list
		
		#TEST Performance
		#for entry in self.list:
		#	if self.recControl.isRecording(entry[0].getPath()):
		#		self.invalidateService(entry[0])
		self.l.invalidate()

	def getNextService(self):
		if not self.currentSelIsDirectory():
			# Cusror marks a movie
			idx = self.getCurrentIndex()
			length = len(self.list)
			for i in xrange(length):
				entry = self.list[(i+idx)%length]
				if entry:
					if entry[2]: 
						# Entry is no directory
						yield entry[0]
		else:
			# Cursor marks a directory
			service = self.getCurrent()
			if service:
				path = service.getPath()
				# Don't play movies from the trash folder or ".."
				if path != config.EMC.movie_trashpath.value and not self.getCurrentSelName() == "..":
					for root, dirs, files in os.walk(path): #,False):
						if dirs:
							for dir in dirs:
								path = os.path.join(root, dir)
								dvdStruct = self.detectDVDStructure( path )
								if dvdStruct:
									path = os.path.dirname(dvdStruct)
									ext = os.path.splitext(dvdStruct)[1].lower()
									yield self.getPlayerService(path, dir, ext)
						if files:
							for name in files:
								global mediaExt
								ext = os.path.splitext(name)[1].lower()
								if ext in mediaExt:
									path = os.path.join(root, name)
									yield self.getPlayerService(path, name, ext)

	def getPlayerService(self, path, name, ext=None):
		global playerDVB, playerDVD, serviceIdDVB, serviceIdDVD, serviceIdMP3, playerMP3
		if not ext:
			service = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + path)
		elif ext in playerDVB:
			service = eServiceReference(serviceIdDVB, 0, path)
		elif ext in playerMP3:
			service = eServiceReference(serviceIdMP3, 0, path)
		elif ext in playerDVD:
			service = eServiceReference(serviceIdDVD, 0, path)
			if service:
				if service.toString().endswith("/VIDEO_TS") or service.toString().endswith("/"):
					names = service.toString().rsplit("/",3)
					if names[2].startswith("Disk ") or names[2].startswith("DVD "):
						name = str(names[1]) + " - " + str(names[2])
					else:
						name = names[2]
					service.setName(str(name))
		elif ext in playerM2TS:
			service = eServiceReference(serviceIdM2TS, 0, path)
		else:
			service = None
		return service

	def currentSelIsDirectory(self):
		try:	return self.list[self.getCurrentIndex()][2] is None
		except:	return False

	def indexIsDirectory(self, index):
		try:	return self.list[index][2] is None
		except:	return False

	def getCurrentSelDir(self):
		service = self.getCurrent()
		return service and service.getPath()

	def getCurrentSelName(self):
		try: return self.list[self.getCurrentIndex()][3]
		except: return "none"

	def getCurrentSelPath(self):
		return self.loadPath + self.list[self.getCurrentIndex()][4] + (self.list[self.getCurrentIndex()][2] is None) * "/"

	def moveToIndex(self, index):
		self.instance.moveSelectionTo(index)

	def moveToService(self, service):
		found = 0
		if service:
			count = 0
			for x in self.list:
				if x[0] == service:
					found = count
				count += 1
		self.instance.moveSelectionTo(found)
