# Copyright (C) 2017 BROADSoftware
#
# This file is part of HADeploy
#
# HADeploy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HADeploy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HADeploy.  If not, see <http://www.gnu.org/licenses/>.

import logging
import hadeploy.core.misc as misc
import os
from hadeploy.core.plugin import Plugin
from hadeploy.core.templator import Templator
from hadeploy.core.const import SRC,DATA,SCOPE_SYSTEMD,ACTION_DEPLOY,ACTION_REMOVE,ACTION_START,ACTION_STOP,SCOPE_SERVICES,SCOPE_SUPERVISOR
from hadeploy.plugins.files.code import lookupInLocalFiles,lookupInLocalTemplates
from sets import Set

logger = logging.getLogger("hadeploy.plugins.systemd")

SYSTEMD_UNITS="systemd_units"
NAME="name"
SCOPE="scope"
UNIT_FILE="unit_file"
NO_REMOVE="no_remove"
_UNIT_FILE_="_unit_file_"


SERVICES="services"

SYSTEMD="systemd"
SCOPE_BY_NAME="scopeByName"     

_SRC_="_src_"
_DISPLAY_SRC_="_displaySrc_"

ENABLED="enabled"
STATE="state"
ST_STARTED="started"
ST_STOPPED="stopped"
ST_CURRENT="current"

ACTION_ON_NOTIFY="action_on_notify"
AON_RESTART="restart"
AON_RELOAD="reload"
AON_NONE="none"

validState= Set([ST_STARTED, ST_STOPPED, ST_CURRENT])
validAon = Set([AON_NONE, AON_RELOAD, AON_RESTART])

SUPERVISORS="supervisors"
USER="user"
GROUP="group"
MANAGED="managed"
CONF_FILE_SRC="conf_file_src"
CONF_FILE_DST="conf_file_dst"
LOGS_DIR="logs_dir"
PID_DIR="pid_dir"
SOCKS_DIR="socks_dir"
INCLUDE_DIR="include_dir"
SUPERVISORCTL="supervisorctl"
HTTP_SERVER="http_server"
ENDPOINT="endpoint"
USERNAME="username"
PASSWORD="password"

# The supervisor.conf file is a double template.
# Rendered a first time during build time (in buildAuxTemplates()), the result is in fact a runtime template, rendered by ansible
# All paths are absolute
CONF_FILE_SRC_JJ2="conf_file_src_jj2"
CONF_FILE_SRC_J2="conf_file_src_j2"
SERVICE_UNIT_JJ2="service_unit_jj2"
SERVICE_UNIT_J2="service_unit_j2"
SUPERVISORCTL_JJ2="supervisorctl_jj2"
SUPERVISORCTL_J2="supervisorctl_j2"


SUPERVISOR_TO_REMOVE_COUNT="supervisorToRemoveCount"
SUPERVISOR_BY_NAME="supervisorByName"

SUPERVISOR="supervisor"
SUPERVISOR_GROUP_BY_NAME="supervisorGroupByName"
SUPERVISOR_PROGRAMS="supervisor_programs"
SUPERVISORPROGRAMS="supervisorPrograms"
COMMAND="command"
SUPERVISOR_OWNER="supervisorOwner"
SUPERVISOR_GROUP="supervisorGroup"
PROGRAM_TO_REMOVE_COUNT="programToRemoveCount"

class ServicesPlugin(Plugin):
    
    def __init__(self, name, path, context):
        Plugin.__init__(self, name, path, context)
           
    def getGroomingPriority(self):
        return 6000     

    def getSupportedScopes(self):
        return [SCOPE_SYSTEMD, SCOPE_SERVICES]        
 
    def getSupportedActions(self):
        return [ACTION_DEPLOY, ACTION_REMOVE,ACTION_START,ACTION_STOP]

    def getPriority(self, action):
        if action == ACTION_DEPLOY:
            return 6000
        elif  action == ACTION_REMOVE:
            return 1800
        elif  action == ACTION_START:
            return 5000
        elif  action == ACTION_STOP:
            return 5000
        else:
            misc.ERROR("Plugin 'systemd' called with invalid action: '{0}'".format(action))


    def onGrooming(self):
        misc.ensureObjectInMaps(self.context.model[DATA], [SERVICES, SCOPE_BY_NAME], {})
        self.groomSystemd()
        self.groomSupervisors()
        self.groomPrograms()
                    
    def groomSystemd(self):
        if self.context.toExclude(SCOPE_SYSTEMD) or self.context.toExclude(SCOPE_SERVICES):
            return
        model = self.context.model
        unitNames = Set()
        if SYSTEMD_UNITS in model[SRC]:
            for unit in model[SRC][SYSTEMD_UNITS]:
                if unit[NAME] in unitNames:
                    misc.ERROR("systemd_unit '{0}' is defined twice!".format(unit[NAME]))
                unitNames.add(unit[NAME]) 
                misc.setDefaultInMap(unit, NO_REMOVE, False)
                misc.setDefaultInMap(unit, ENABLED, True)
                misc.setDefaultInMap(unit, STATE, ST_CURRENT)
                if unit[STATE] not in validState:
                    misc.ERROR("Systemd_unit {0}: state value '{1}' is not valid. Must be one of {2}".format(unit[NAME], unit[STATE], validState))
                misc.setDefaultInMap(unit, ACTION_ON_NOTIFY, AON_RESTART)
                if unit[ACTION_ON_NOTIFY] not in validAon:
                    misc.ERROR("Systemd_unit {0}: action_on_notify value '{1}' is not valid. Must be one of {2}".format(unit[NAME], unit[ACTION_ON_NOTIFY], validAon))
                # ---------------------- Lookup unit file
                path, displaySrc, errMsg = lookupSrc(model, unit[UNIT_FILE])
                if path != None:
                    unit[_UNIT_FILE_] = path
                    unit[_DISPLAY_SRC_] = displaySrc
                else:
                    misc.ERROR("Systemd_unit '{0}': {1}".format(unit[NAME], errMsg))
                # ---------------------- Insert in scope
                if not self.context.checkScope(unit[SCOPE]):
                    misc.ERROR("Systemd_unit {0}: scope attribute '{1}' does not match any host or host_group!".format(unit[NAME], unit[SCOPE]))
                else:
                    misc.ensureObjectInMaps(self.context.model[DATA][SERVICES][SCOPE_BY_NAME], [unit[SCOPE], SYSTEMD], [])
                    model[DATA][SERVICES][SCOPE_BY_NAME][unit[SCOPE]][SYSTEMD].append(unit)
    
    def groomSupervisors(self):
        if self.context.toExclude(SCOPE_SUPERVISOR) or self.context.toExclude(SCOPE_SERVICES):
            return
        model = self.context.model
        if SUPERVISORS in model[SRC]:
            misc.ensureObjectInMaps(self.context.model[DATA][SERVICES], [SUPERVISOR_BY_NAME], {})
            for supervisord in model[SRC][SUPERVISORS]:
                if supervisord[NAME] in self.context.model[DATA][SERVICES][SUPERVISOR_BY_NAME]:
                    misc.ERROR("supervisor '{0}' is defined twice!".format(supervisord[NAME]))
                self.context.model[DATA][SERVICES][SUPERVISOR_BY_NAME][supervisord[NAME]] = supervisord                    
                misc.setDefaultInMap(supervisord, MANAGED, True)
                if not supervisord[MANAGED]:
                    misc.ERROR("TODO")
                else:
                    self.groomOneSupervisord(model, supervisord)
                # ---------------------- Insert in scope
                if not self.context.checkScope(supervisord[SCOPE]):
                    misc.ERROR("Supervisor {0}: scope attribute '{1}' does not match any host or host_group!".format(supervisord[NAME], supervisord[SCOPE]))
                else:
                    misc.ensureObjectInMaps(self.context.model[DATA][SERVICES][SCOPE_BY_NAME], [supervisord[SCOPE], SUPERVISORS], [])
                    model[DATA][SERVICES][SCOPE_BY_NAME][supervisord[SCOPE]][SUPERVISORS].append(supervisord)
            # We need the number of supervisor to remove per scope, to help in template
            for _, scope in  model[DATA][SERVICES][SCOPE_BY_NAME].iteritems():
                if SUPERVISORS in scope:
                    count = 0
                    for supervisord in scope[SUPERVISORS]:
                        if not supervisord[NO_REMOVE]:
                            count += 1
                    scope[SUPERVISOR_TO_REMOVE_COUNT] = count

    def groomOneSupervisord(self, model, supervisord):
        misc.setDefaultInMap(supervisord, CONF_FILE_DST, "/etc/supervisord_{0}.conf".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, LOGS_DIR, "/var/log/supervisor_{0}".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, PID_DIR, "/var/run/supervisor_{0}".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, SOCKS_DIR, "/var/run/supervisor_{0}".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, INCLUDE_DIR, "/etc/supervisord_{0}.d".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, SUPERVISORCTL, "/usr/bin/supervisorctl_{0}".format(supervisord[NAME]))
        misc.setDefaultInMap(supervisord, NO_REMOVE, False)
        misc.setDefaultInMap(supervisord, ENABLED, True)
        misc.setDefaultInMap(supervisord, STATE, ST_CURRENT)
        if HTTP_SERVER in supervisord:
            misc.setDefaultInMap(supervisord[HTTP_SERVER], ENDPOINT, "127.0.0.1:9001")
            if PASSWORD in supervisord[HTTP_SERVER]:
                misc.setDefaultInMap(supervisord[HTTP_SERVER], USERNAME, supervisord[USER])
        if CONF_FILE_SRC in supervisord:
            path, _, errMsg = lookupSrc(model, supervisord[CONF_FILE_SRC])
            if path != None:
                supervisord[CONF_FILE_SRC_JJ2] = path
            else:
                misc.ERROR("Supervisor '{0}': {1}".format(supervisord[NAME], errMsg))
        else:
            supervisord[CONF_FILE_SRC_JJ2] = os.path.join(self.path, "templates/supervisord.conf.jj2")
        supervisord[CONF_FILE_SRC_J2] = "supervisord_{0}.conf.j2".format(supervisord[NAME])
        supervisord[SERVICE_UNIT_JJ2] = os.path.join(self.path, "templates/supervisord.service.jj2")
        supervisord[SERVICE_UNIT_J2] = "supervisord_{0}.service.j2".format(supervisord[NAME])
        supervisord[SUPERVISORCTL_JJ2] = os.path.join(self.path, "templates/supervisorctl.jj2")
        supervisord[SUPERVISORCTL_J2] = "supervisorctl_{0}".format(supervisord[NAME])
            

    def groomPrograms(self):
        if self.context.toExclude(SCOPE_SUPERVISOR) or self.context.toExclude(SCOPE_SERVICES):
            return
        model = self.context.model
        if SUPERVISOR_PROGRAMS in model[SRC]:
            for prg in model[SRC][SUPERVISOR_PROGRAMS]:
                if not prg[SUPERVISOR] in model[DATA][SERVICES][SUPERVISOR_BY_NAME]:
                    misc.ERROR("supervisor_program '{}' refer to an undefined supervisor '{}'".format(prg[NAME], prg[SUPERVISOR]))
                else:
                    supervisord = model[DATA][SERVICES][SUPERVISOR_BY_NAME][prg[SUPERVISOR]]
                misc.setDefaultInMap(prg, NO_REMOVE, False)
                if prg[NO_REMOVE] and not supervisord[NO_REMOVE]:
                    misc.ERROR("Supervisor_program '{}' has no remove flag set while its supervisor ({}) has not!".format(prg[NAME], supervisord[NAME]))
                if CONF_FILE_SRC in prg:
                    path, _, errMsg = lookupSrc(model, prg[CONF_FILE_SRC])
                    if path != None:
                        prg[CONF_FILE_SRC_JJ2] = path
                    else:
                        misc.ERROR("Supervisor_program '{0}': {1}".format(prg[NAME], errMsg))
                else:
                    prg[CONF_FILE_SRC_JJ2] = os.path.join(self.path, "templates/program.conf.jj2")
                    if COMMAND not in prg:
                        misc.ERROR("Supervisor_program '{}': A 'command' parameter must be provided if using the default configuration file (No 'conf_file_src' parameter".format(prg[NAME]))
                prg[CONF_FILE_SRC_J2] = "supervisor_{}_program_{}.conf".format(supervisord[NAME], prg[NAME])
                prg[CONF_FILE_DST] = os.path.join(supervisord[INCLUDE_DIR], "{}.init".format(prg[NAME]))
                prg[SUPERVISOR_OWNER] = supervisord[USER]
                prg[SUPERVISOR_GROUP] = supervisord[GROUP]
                # Note we don't set prg[USER], as we want to be unset in config file if not set
                
                # ---------------------- Insert in scope
                misc.ensureObjectInMaps(self.context.model[DATA][SERVICES][SCOPE_BY_NAME], [supervisord[SCOPE], SUPERVISORPROGRAMS], [])
                model[DATA][SERVICES][SCOPE_BY_NAME][supervisord[SCOPE]][SUPERVISORPROGRAMS].append(prg)
            # We need the number of supervisor to remove per scope, to help in template
            for _, scope in  model[DATA][SERVICES][SCOPE_BY_NAME].iteritems():
                if SUPERVISORPROGRAMS in scope:
                    count = 0
                    for prg in scope[SUPERVISORPROGRAMS]:
                        if not prg[NO_REMOVE]:
                            count += 1
                    scope[PROGRAM_TO_REMOVE_COUNT] = count
                        
                
            
    
    def buildAuxTemplates(self, action, priority):
        if self.context.toExclude(SCOPE_SUPERVISOR) or self.context.toExclude(SCOPE_SERVICES):
            return
        if action != ACTION_DEPLOY:
            return
        model = self.context.model
        if SUPERVISORS in model[SRC]:
            for supervisord in model[SRC][SUPERVISORS]:
                templator = Templator(["/"], supervisord)    # All template path are absolute
                templator.generate(supervisord[CONF_FILE_SRC_JJ2], os.path.join(self.context.workingFolder, supervisord[CONF_FILE_SRC_J2]))
                templator.generate(supervisord[SERVICE_UNIT_JJ2],  os.path.join(self.context.workingFolder, supervisord[SERVICE_UNIT_J2]))
                templator.generate(supervisord[SUPERVISORCTL_JJ2],  os.path.join(self.context.workingFolder, supervisord[SUPERVISORCTL_J2]))
        if SUPERVISOR_PROGRAMS in model[SRC]:
            for prg in model[SRC][SUPERVISOR_PROGRAMS]:
                templator = Templator(["/"], prg)    # All template path are absolute
                templator.generate(prg[CONF_FILE_SRC_JJ2], os.path.join(self.context.workingFolder, prg[CONF_FILE_SRC_J2]))



def lookupSrc(model, src):
    if src.startswith("file://"):
        path = src[len('file://'):] 
        displaySrc = path
        if not path.startswith("/"):
            path = lookupInLocalFiles(path, model)
        else:
            if not os.path.exists(path):
                return (None, None, "'{0}' does not exists".format(path))
        if os.path.isdir(path):
            return (None, None, "'{0}' can't be a folder!".format(src))
        return (path, displaySrc, None)
    elif src.startswith("tmpl://"):
        path = src[len('tmpl://'):] 
        displaySrc = path
        if not path.startswith("/"):
            path = lookupInLocalTemplates(path, model)
        else:
            if not os.path.exists(path):
                misc.ERROR("'{0}' does not exists".format(path))
        if os.path.isdir(path):
            misc.ERROR("Unit_file '{0}' can't be a folder!".format(src))
        return(path, displaySrc, None)
    else:
        return (None, None, "{0} is not a valid form. Unknown scheme.".format(src))




    
                
