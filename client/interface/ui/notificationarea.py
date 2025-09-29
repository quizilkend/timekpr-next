"""
Created on Aug 28, 2018

@author: mjasnik
"""

# import
from datetime import timedelta
import os

# timekpr imports
from timekpr.common.constants import constants as cons
from timekpr.common.log import log
from timekpr.client.interface.dbus.notifications import timekprNotifications
from timekpr.client.gui.clientgui import timekprGUI


class timekprNotificationArea(object):
    """Support appindicator or other means of showing icon on the screen (this class is a parent for classes like indicator or staticon)"""

    def __init__(self, pUserName, pUserNameFull, pTimekprClientConfig):
        """Init all required stuff for indicator"""

        log.log(cons.TK_LOG_LEVEL_INFO, "start init timekpr indicator")

        # configuration
        self._timekprClientConfig = pTimekprClientConfig

        # set version
        self._timekprVersion = "-.-.-"
        # set username
        self._userName = pUserName
        # initialize priority
        self._lastUsedPriority = self._lastUsedServerPriority = ""
        # priority level
        self._lastUsedPriorityLvl = -99
        # PlayTime priority level
        self._lastUsedPTPriorityLvl = -99
        # initialize time left
        self._timeLeftTotal = None
        # initialize PlayTime left
        self._playTimeLeftTotal = None
        # initialize time limit
        self._timeNotLimited = 0

        # init notificaction stuff
        self._timekprNotifications = timekprNotifications(self._userName, self._timekprClientConfig)

        # dbus
        self._timekprBus = None
        self._notifyObject = None
        self._notifyInterface = None

        # gui forms
        self._timekprGUI = timekprGUI(cons.TK_VERSION, self._timekprClientConfig, self._userName, pUserNameFull)

        log.log(cons.TK_LOG_LEVEL_INFO, "finish init timekpr indicator")

    def initClientConnections(self):
        """Proxy method for initialization"""
        # initalize DBUS connections to every additional module
        self._timekprNotifications.initClientConnections()

    def isTimekprConnected(self):
        """Proxy method for initialization status"""
        # check if main connection to timekpr is up
        return self._timekprNotifications.isTimekprConnected()

    def verifySessionAttributes(self, pWhat, pKey):
        """Proxy method for receive the signal and process the data"""
        self._timekprNotifications.verifySessionAttributes(pWhat, pKey)

    def requestTimeLimits(self):
        """Proxy method for request time limits from server"""
        self._timekprNotifications.requestTimeLimits()

    def requestTimeLeft(self):
        """Proxy method for request time left from server"""
        self._timekprNotifications.requestTimeLeft()

    def _determinePriority(self, pType, pPriority, pTimeLeft):
        """Determine priority based on client config"""
        # def
        finalPrio = pPriority
        finalLimitSecs = -1
        # keep in mind that this applies to timeLeft only and critical notifications can STILL be pushed from server
        if pTimeLeft is not None:
            # calculate
            for rPrio in self._timekprClientConfig.getClientNotificationLevels() if pType == "Time" else self._timekprClientConfig.getClientPlayTimeNotificationLevels():
                # determine which is the earliest priority level we need to use
                # it is determined as time left is less then this interval
                if rPrio[0] >= pTimeLeft and (finalLimitSecs > rPrio[0] or finalLimitSecs < 0):
                    # determine if this is the gratest level that is lower than limit
                    finalLimitSecs = rPrio[0]
                    finalPrio = cons.TK_PRIO_LVL_MAP[rPrio[1]]
        # final priority
        return finalPrio, finalLimitSecs

    def formatTimeLeft(self, pPriority, pTimeLeft, pTimeNotLimited, pPlayTimeLeft=None):
        """Set time left in the indicator"""
        log.log(cons.TK_LOG_LEVEL_DEBUG, "start formatTimeLeft")

        # prio
        prio = pPriority
        timekprIcon = None
        timeLeftStr = None
        isTimeChanged = self._timeLeftTotal != pTimeLeft
        isPlayTimeChanged = self._playTimeLeftTotal != pPlayTimeLeft

        # determine hours and minutes for PlayTime (if there is such time)
        if (isTimeChanged or isPlayTimeChanged) and pPlayTimeLeft is not None and pTimeLeft is not None:
            # get the smallest one
            timeLeftPT = min(pPlayTimeLeft, pTimeLeft)
            # determine hours and minutes
            timeLeftStrPT = str((timeLeftPT - cons.TK_DATETIME_START).days * 24 + timeLeftPT.hour).rjust(2, "0")
            timeLeftStrPT += ":" + str(timeLeftPT.minute).rjust(2, "0")
            timeLeftStrPT += ((":" + str(timeLeftPT.second).rjust(2, "0")) if self._timekprClientConfig.getClientShowSeconds() else "")

        # execute time and icon changes + notifications only when there are changes
        if isTimeChanged or isPlayTimeChanged or pTimeLeft is None or self._lastUsedServerPriority != pPriority:
            # if there is no time left set yet, show --
            if pTimeLeft is None:
                # determine hours and minutes
                timeLeftStr = "--:--" + (":--" if self._timekprClientConfig.getClientShowSeconds() else "")
            else:
                # update time
                self._timeLeftTotal = pTimeLeft
                self._playTimeLeftTotal = pPlayTimeLeft
                self._timeNotLimited = pTimeNotLimited

                # unlimited has special icon and text (if it's not anymore, these will change)
                if self._timeNotLimited > 0:
                    # unlimited!
                    timeLeftStr = "∞"
                    prio = "unlimited"
                else:
                    # create detailed tooltip with multiple lines
                    timeLeftStr = self._formatDetailedTooltip(pTimeLeft, pPlayTimeLeft)

                    # notifications and icons only when time has changed
                    if isTimeChanged:
                        # get user configured level and priority
                        prio, finLvl = (pPriority, -1) if pPriority == cons.TK_PRIO_UACC else self._determinePriority("Time", pPriority, (pTimeLeft - cons.TK_DATETIME_START).total_seconds())

                        # if level actually changed
                        if self._lastUsedPriorityLvl != finLvl:
                            # do not notify if this is the first invocation, because initial limits are already asked from server
                            # do not notify user in case icon is hidden and no notifications should be shown
                            if self._lastUsedPriorityLvl > 0 and self.getTrayIconEnabled():
                                # emit notification
                                self.notifyUser(cons.TK_MSG_CODE_TIMELEFT, None, prio, pTimeLeft, None)
                            # level this up
                            self._lastUsedPriorityLvl = finLvl

                # now, if priority changes, set up icon as well
                if isTimeChanged and self._lastUsedPriority != prio:
                    # log
                    log.log(cons.TK_LOG_LEVEL_DEBUG, "changing icon for level, old: %s, new: %s" % (self._lastUsedPriority, prio))
                    # set up last used prio
                    self._lastUsedPriority = prio
                    # get status icon
                    timekprIcon = os.path.join(self._timekprClientConfig.getTimekprSharedDir(), "icons", cons.TK_PRIO_CONF[cons.getNotificationPrioriy(self._lastUsedPriority)][cons.TK_ICON_STAT])

            # adjust server priority: server sends all time left messages with low priority, except when there is no time left, then priority is critical
            self._lastUsedServerPriority = pPriority

        log.log(cons.TK_LOG_LEVEL_DEBUG, "finish formatTimeLeft")

        # return time left and icon (if changed), so implementations can use it
        return timeLeftStr, timekprIcon

    def _formatDetailedTooltip(self, pTimeLeft, pPlayTimeLeft):
        """Format detailed tooltip with all time information"""
        tooltip_lines = []
        
        # Helper function to format time similar to formatTimeStr with short format
        def format_time_short(time_obj):
            if time_obj is None:
                return "--:--"
            days = (time_obj - cons.TK_DATETIME_START).days
            hours = time_obj.hour + (days * 24)
            minutes = time_obj.minute
            return "%s:%s" % (str(hours).rjust(2, "0"), str(minutes).rjust(2, "0"))
        
        # Get time information from GUI if available
        gui = self._timekprGUI
        if gui and hasattr(gui, '_timeSpent'):
            # Debug logging to understand what data is available
            log.log(cons.TK_LOG_LEVEL_DEBUG, "Tooltip debug - GUI attributes available:")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpent: {getattr(gui, '_timeSpent', 'NOT_FOUND')}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpentWeek: {getattr(gui, '_timeSpentWeek', 'NOT_FOUND')}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpentPT: {getattr(gui, '_timeSpentPT', 'NOT_FOUND')}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpentPTWeek: {getattr(gui, '_timeSpentPTWeek', 'NOT_FOUND')}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeLeftPTWeek: {getattr(gui, '_timeLeftPTWeek', 'NOT_FOUND')}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _limitConfig keys: {list(gui._limitConfig.keys()) if hasattr(gui, '_limitConfig') and gui._limitConfig else 'NOT_FOUND'}")
            if hasattr(gui, '_limitConfig') and gui._limitConfig and cons.TK_CTRL_PTLMT in gui._limitConfig:
                log.log(cons.TK_LOG_LEVEL_DEBUG, f"  PlayTime config structure: {gui._limitConfig[cons.TK_CTRL_PTLMT]}")
            
            # Daily time info - always show
            daily_spent = format_time_short(getattr(gui, '_timeSpent', None))
            daily_limit = "--:--"
            
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  daily_spent: {daily_spent} (from _timeSpent: {getattr(gui, '_timeSpent', None)})")
            
            # Get daily limit from configuration
            if hasattr(gui, '_limitConfig') and gui._limitConfig:
                from datetime import datetime
                current_day = str(datetime.now().isoweekday())
                log.log(cons.TK_LOG_LEVEL_DEBUG, f"  current_day: {current_day}")
                if current_day in gui._limitConfig and cons.TK_CTRL_LIMITD in gui._limitConfig[current_day]:
                    daily_limit_seconds = gui._limitConfig[current_day][cons.TK_CTRL_LIMITD]
                    log.log(cons.TK_LOG_LEVEL_DEBUG, f"  daily_limit_seconds: {daily_limit_seconds}")
                    if daily_limit_seconds is not None:
                        daily_limit_time = cons.TK_DATETIME_START + timedelta(seconds=daily_limit_seconds)
                        daily_limit = format_time_short(daily_limit_time)
            
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  final daily_limit: {daily_limit}")
            tooltip_lines.append("Daily: %s/%s" % (daily_spent, daily_limit))
            
            # Weekly time info - always show if available
            weekly_spent = format_time_short(getattr(gui, '_timeSpentWeek', None))
            weekly_limit = "--:--"
            
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  weekly_spent: {weekly_spent} (from _timeSpentWeek: {getattr(gui, '_timeSpentWeek', None)})")
            
            # Get weekly limit from configuration
            if hasattr(gui, '_limitConfig') and gui._limitConfig and cons.TK_CTRL_LIMITW in gui._limitConfig:
                weekly_limit_seconds = gui._limitConfig[cons.TK_CTRL_LIMITW].get(cons.TK_CTRL_LIMITW)
                log.log(cons.TK_LOG_LEVEL_DEBUG, f"  weekly_limit_seconds: {weekly_limit_seconds}")
                if weekly_limit_seconds is not None:
                    weekly_limit_time = cons.TK_DATETIME_START + timedelta(seconds=weekly_limit_seconds)
                    weekly_limit = format_time_short(weekly_limit_time)
            
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  final weekly_limit: {weekly_limit}")
            tooltip_lines.append("Weekly: %s/%s" % (weekly_spent, weekly_limit))
            
            # PlayTime info - Always try to show if any PlayTime data exists
            # Get PlayTime values first
            pt_daily_spent = format_time_short(getattr(gui, '_timeSpentPT', None))
            pt_weekly_spent = format_time_short(getattr(gui, '_timeSpentPTWeek', None))
            pt_daily_limit = "--:--"
            pt_weekly_limit = "--:--"
            
            # Check if we have ANY PlayTime-related information
            has_pt_data = (hasattr(gui, '_timeSpentPT') and gui._timeSpentPT is not None) or \
                         (hasattr(gui, '_timeSpentPTWeek') and gui._timeSpentPTWeek is not None) or \
                         (hasattr(gui, '_timeLeftPTWeek') and gui._timeLeftPTWeek is not None)
            
            # Also check if PlayTime is configured
            has_pt_config = (hasattr(gui, '_limitConfig') and gui._limitConfig and 
                           (cons.TK_CTRL_PTTLE in gui._limitConfig or cons.TK_CTRL_PTLMT in gui._limitConfig))
            
            # Show PlayTime if we have data OR configuration
            show_playtime = has_pt_data or has_pt_config
            
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"Tooltip PlayTime debug:")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  pt_daily_spent: {pt_daily_spent}")  
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  pt_weekly_spent: {pt_weekly_spent}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  has_pt_data: {has_pt_data}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  has_pt_config: {has_pt_config}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  show_playtime: {show_playtime}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpentPT exists: {hasattr(gui, '_timeSpentPT') and gui._timeSpentPT is not None}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeSpentPTWeek exists: {hasattr(gui, '_timeSpentPTWeek') and gui._timeSpentPTWeek is not None}")
            log.log(cons.TK_LOG_LEVEL_DEBUG, f"  _timeLeftPTWeek exists: {hasattr(gui, '_timeLeftPTWeek') and gui._timeLeftPTWeek is not None}")
            
            if show_playtime:
                
                # Get PlayTime daily limit from configuration
                if hasattr(gui, '_limitConfig') and gui._limitConfig and cons.TK_CTRL_PTLMT in gui._limitConfig:
                    from datetime import datetime
                    current_day = str(datetime.now().isoweekday())
                    
                    pt_limits = gui._limitConfig[cons.TK_CTRL_PTLMT]
                    log.log(cons.TK_LOG_LEVEL_DEBUG, f"  pt_limits type: {type(pt_limits)}")
                    
                    if isinstance(pt_limits, dict) and cons.TK_CTRL_PTLMT in pt_limits:
                        # List format: [["1", limit], ["2", limit], ...]
                        for day_config in pt_limits[cons.TK_CTRL_PTLMT]:
                            if isinstance(day_config, list) and len(day_config) >= 2 and day_config[0] == current_day:
                                if day_config[1] is not None and day_config[1] > 0:
                                    pt_daily_limit_time = cons.TK_DATETIME_START + timedelta(seconds=day_config[1])
                                    pt_daily_limit = format_time_short(pt_daily_limit_time)
                                break
                
                # Calculate weekly PlayTime limit from spent + left time (since weekly limit isn't in config)
                if hasattr(gui, '_timeSpentPTWeek') and hasattr(gui, '_timeLeftPTWeek'):
                    pt_weekly_spent_obj = getattr(gui, '_timeSpentPTWeek', None)
                    pt_weekly_left_obj = getattr(gui, '_timeLeftPTWeek', None)
                    
                    log.log(cons.TK_LOG_LEVEL_DEBUG, f"  pt_weekly_spent_obj: {pt_weekly_spent_obj}")
                    log.log(cons.TK_LOG_LEVEL_DEBUG, f"  pt_weekly_left_obj: {pt_weekly_left_obj}")
                    
                    if pt_weekly_spent_obj is not None and pt_weekly_left_obj is not None:
                        # Weekly limit = weekly spent + weekly left
                        weekly_spent_seconds = (pt_weekly_spent_obj - cons.TK_DATETIME_START).total_seconds()
                        weekly_left_seconds = (pt_weekly_left_obj - cons.TK_DATETIME_START).total_seconds()
                        weekly_limit_seconds = weekly_spent_seconds + weekly_left_seconds
                        
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  weekly_spent_seconds: {weekly_spent_seconds}")
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  weekly_left_seconds: {weekly_left_seconds}")
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  weekly_limit_seconds: {weekly_limit_seconds}")
                        
                        if weekly_limit_seconds > 0:
                            pt_weekly_limit_time = cons.TK_DATETIME_START + timedelta(seconds=weekly_limit_seconds)
                            pt_weekly_limit = format_time_short(pt_weekly_limit_time)
                        else:
                            # Even if limit is 0, show it as 00:00 instead of --:--
                            pt_weekly_limit = "00:00"
                        
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  calculated weekly limit: {pt_weekly_limit}")
                    else:
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  Cannot calculate weekly limit - missing data")
                
                # Override pt_weekly_spent if it shows --:-- but we have data
                if pt_weekly_spent == "--:--" and hasattr(gui, '_timeSpentPTWeek'):
                    pt_weekly_spent_obj = getattr(gui, '_timeSpentPTWeek', None)
                    if pt_weekly_spent_obj is not None:
                        # Recalculate the spent time formatting
                        pt_weekly_spent = format_time_short(pt_weekly_spent_obj)
                        log.log(cons.TK_LOG_LEVEL_DEBUG, f"  recalculated pt_weekly_spent: {pt_weekly_spent}")
                
                log.log(cons.TK_LOG_LEVEL_DEBUG, f"  final limits - daily: {pt_daily_limit}, weekly: {pt_weekly_limit}")
                tooltip_lines.append("Daily PlayTime: %s/%s" % (pt_daily_spent, pt_daily_limit))
                tooltip_lines.append("Weekly PlayTime: %s/%s" % (pt_weekly_spent, pt_weekly_limit))
        
        # Fallback to original simple format if no detailed info available
        if not tooltip_lines:
            simple_time = str((pTimeLeft - cons.TK_DATETIME_START).days * 24 + pTimeLeft.hour).rjust(2, "0")
            simple_time += ":" + str(pTimeLeft.minute).rjust(2, "0")
            simple_time += ((":" + str(pTimeLeft.second).rjust(2, "0")) if self._timekprClientConfig.getClientShowSeconds() else "")
            
            if pPlayTimeLeft is not None:
                timeLeftPT = min(pPlayTimeLeft, pTimeLeft)
                timeLeftStrPT = str((timeLeftPT - cons.TK_DATETIME_START).days * 24 + timeLeftPT.hour).rjust(2, "0")
                timeLeftStrPT += ":" + str(timeLeftPT.minute).rjust(2, "0")
                timeLeftStrPT += ((":" + str(timeLeftPT.second).rjust(2, "0")) if self._timekprClientConfig.getClientShowSeconds() else "")
                return "%s / %s" % (simple_time, timeLeftStrPT)
            return simple_time
        
        return "\n".join(tooltip_lines)

    def processPlayTimeNotifications(self, pTimeLimits):
        """Process PlayTime notifications (if there is PT info in limits)"""
        isPTInfoEnabled = self._timekprGUI.isPlayTimeAccountingInfoEnabled()
        # determine whether we actually need to process PlayTime
        if cons.TK_CTRL_PTLSTC in pTimeLimits and cons.TK_CTRL_PTLPD in pTimeLimits and cons.TK_CTRL_PTTLO in pTimeLimits:
            # only of not enabled
            if not isPTInfoEnabled:
                self._timekprGUI.setPlayTimeAccountingInfoEnabled(True)
            # get user configured level and priority
            prio, finLvl = self._determinePriority("PlayTime", cons.TK_PRIO_LOW, pTimeLimits[cons.TK_CTRL_PTLPD])
            # log
            log.log(cons.TK_LOG_LEVEL_DEBUG, "process PT notif, prio: %s, prevLVL: %i, lvl: %i, icoena: %s" % (prio, self._lastUsedPTPriorityLvl, finLvl, self.getTrayIconEnabled()))
            # if any priority is effective, determine whether we need to inform user
            if (finLvl > 0 or self._lastUsedPTPriorityLvl < -1) and self._lastUsedPTPriorityLvl != finLvl and self.isTimekprConnected():
                # adjust level too
                self._lastUsedPTPriorityLvl = finLvl
                # if icon is hidden, do not show any notifications
                if self.getTrayIconEnabled():
                    # notify user
                    self._timekprNotifications.notifyUser(cons.TK_MSG_CODE_TIMELEFT, "PlayTime", prio, cons.TK_DATETIME_START + timedelta(seconds=min(pTimeLimits[cons.TK_CTRL_PTLPD], pTimeLimits[cons.TK_CTRL_LEFTD])), None)
        elif isPTInfoEnabled:
            # disable info (if it was enabled)
            log.log(cons.TK_LOG_LEVEL_DEBUG, "disable PT info tab")
            self._timekprGUI.setPlayTimeAccountingInfoEnabled(False)

    def notifyUser(self, pMsgCode, pMsgType, pPriority, pTimeLeft=None, pAdditionalMessage=None):
        """Notify user (a wrapper call)"""
        # prio
        prio = pPriority
        timeLeft = cons.TK_DATETIME_START if pTimeLeft is None else pTimeLeft
        # for time left, we need to determine final priority accoriding to user defined priority (if not defined, that will come from server)
        if pMsgCode == cons.TK_MSG_CODE_TIMELEFT:
            # get user configured level and priority
            prio, finLvl = self._determinePriority("Time", pPriority, (timeLeft - cons.TK_DATETIME_START).total_seconds())
        #  notify user
        self._timekprNotifications.notifyUser(pMsgCode, pMsgType, prio, timeLeft, pAdditionalMessage)

    def setStatus(self, pStatus):
        """Change status of timekpr"""
        return self._timekprGUI.setStatus(pStatus)

    # --------------- user clicked methods --------------- #

    def invokeTimekprTimeLeft(self, pEvent):
        """Inform user about (almost) exact time left"""
        # inform user about precise time
        self.notifyUser((cons.TK_MSG_CODE_TIMEUNLIMITED if self._timeNotLimited > 0 else cons.TK_MSG_CODE_TIMELEFT), None, self._lastUsedPriority, self._timeLeftTotal)

    def invokeTimekprUserProperties(self, pEvent):
        """Bring up a window for property editing"""
        # show limits and config
        self._timekprGUI.initConfigForm()

    def invokeTimekprAbout(self, pEvent):
        """Bring up a window for timekpr configration (this needs elevated privileges to do anything)"""
        # show about
        self._timekprGUI.initAboutForm()

    # --------------- configuration update methods --------------- #

    def renewUserLimits(self, pTimeInformation):
        """Call an update to renew time left"""
        # pass this to actual gui storage
        self._timekprGUI.renewLimits(pTimeInformation)

    def renewLimitConfiguration(self, pLimits):
        """Call an update on actual limits"""
        # pass this to actual gui storage
        self._timekprGUI.renewLimitConfiguration(pLimits)
