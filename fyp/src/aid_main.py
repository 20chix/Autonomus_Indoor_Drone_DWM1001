#!/usr/bin/env python

from aid_systemDefinitions       import SYS_DEFS

__author__     = SYS_DEFS.AUTHOR
__version__    = SYS_DEFS.VERSION
__maintainer__ = SYS_DEFS.MAINTAINER
__email__      = SYS_DEFS.EMAIL
__status__     = SYS_DEFS.STATUS

import rospy
import time
from std_msgs.msg                import Empty
from fyp.cfg                     import droneGUIConfig
from dynamic_reconfigure.server  import Server
from nav_msgs.msg                import Odometry
from aid_lastDroneData           import lastDroneDataClass
from ardrone_autonomy.msg        import Navdata
from aid_loadWaypointsInGazebo   import LoadWaypointsInGazebo
from aid_loadDwm1001InGazebo     import LoadDwm1001InGazebo
from aid_waypoints               import DroneWaypoint
from sensor_msgs.msg             import Joy
from localizer_dwm1001.msg       import Anchor
from localizer_dwm1001.msg       import Tag
from std_srvs.srv                import Trigger, TriggerRequest
from localizer_dwm1001.srv       import Anchor_0


import math
from geometry_msgs.msg import (
    PoseWithCovariance,
    Pose,
    Twist,
)

navDataRotZ    = 0
navDataRotZ360 = 0
actionCode     = 0

latchStartTime        = rospy.Duration(5.0)
externalEstimatedPose = PoseWithCovariance()
lastSavedWayHomePoint = Pose()
targetInDrone         = Pose()
land_msg              = Empty()
takeoff_msg           = Empty()
reset_msg             = Empty()
messageTwist          = Twist()
targetInDrone         = Pose()
targetInMap           = Pose()
lastSavedWaypoint     = Pose()
realPose              = PoseWithCovariance()
droneWaypointsFromXML = DroneWaypoint()


firstTimeSamplingData = True
latched               = False


targetInMap.position.x = 0
targetInMap.position.y = 0
targetInMap.position.z = 0
targetInMap.orientation.x = 0
targetInMap.orientation.y = 0
targetInMap.orientation.z = 0

lastSavedWaypoint.position.x = 0
lastSavedWaypoint.position.y = 0
lastSavedWaypoint.position.z = 0

currentWaypointCounterForFlightPath = 0
currentWaypointCounterForFlightPathDWM1001 = 0
currentSavedWaypointPtr = 0

poseEstimationMethod = 1

externalEstimatedPose.pose.position.x = 0
externalEstimatedPose.pose.position.y = 0
externalEstimatedPose.pose.position.z = 0

#Create two instances of lastDroneDataClass
lastDroneData    = lastDroneDataClass()
currentDroneData = lastDroneDataClass()


lastDroneData.xRot = 0
lastDroneData.yRot = 0
lastDroneData.zRot = 0


wayHomePtr = -1


lastSavedWayHomePoint.position.x = 0
lastSavedWayHomePoint.position.y = 0
lastSavedWayHomePoint.position.z = 0.1




gazeboDwm1001 = LoadDwm1001InGazebo()


# Setup a node 
rospy.init_node('fyp', anonymous=False)
lastDataSampleTime = rospy.Time()
rate = rospy.Rate(50)

# Define publishers and messages that will be used
pub_cmd_vel  = rospy.Publisher('/cmd_vel'             , Twist, queue_size=1)
pub_takeoff  = rospy.Publisher('/ardrone/takeoff'     , Empty, queue_size=1)
pub_land     = rospy.Publisher('/ardrone/land'        , Empty, queue_size=1)
pub_reset    = rospy.Publisher("ardrone/reset"        , Empty, queue_size=1)




def init():
    """Initialise ROS time,
    drone linear and angular velocity
    and subscribe to /ardrone/navdata and /ground_truth/state

    :argument

    """
    global messageTwist, lastDroneData

    #Initialise last and current drone data to ros time
    lastDroneData.timeStamp = rospy.Time()
    currentDroneData.timeStamp = rospy.Time()

    #Initialise message twist to 0
    messageTwist = setUpTwist(0, 0, 0, 0, 0, 0)

    #Initialise Dynamic configuration
    Server(droneGUIConfig, droneGUICallback)

    #Subscribe to these topics
    rospy.Subscriber('/ardrone/navdata', Navdata, navDataCallBack)
    rospy.Subscriber('/ground_truth/state', Odometry, realPoseCallBack)
    rospy.Subscriber("joy", Joy, JoystickCallBack)


    # gazeboWaypoints = LoadWaypointsInGazebo()
    # gazeboWaypoints.addWaypointsFromXMLToGazebo()
    
    
    # gazeboDwm1001 = LoadDwm1001InGazebo()
    # gazeboDwm1001.execute()

    run()



# TODO delete this, Here for reference
# # Porportional Controller
# # linear velocity in the x-axis:
# vel_msg.linear.x = 1.5 * sqrt(pow((goal_pose.x - self.pose.x), 2) + pow((goal_pose.y - self.pose.y), 2))
# vel_msg.linear.y = 0
# vel_msg.linear.z = 0
#
# # angular velocity in the z-axis:
# vel_msg.angular.x = 0
# vel_msg.angular.y = 0
# vel_msg.angular.z = 4 * (atan2(goal_pose.y - self.pose.y, goal_pose.x - self.pose.x) - self.pose.theta)




def run():
    """
    Based on the received command, land,takeoff, go to a waypoint, pivot and go to waypoint or go to origin

    """
    global currentDroneData , actionCode, targetInMap, latchStartTime, latched, wayHomePtr, pub_cmd_vel, pub_takeoff, pub_land, pub_reset
    latchTime = rospy.Duration(5.0)
    rospy.loginfo("Waiting for a command")


    while not rospy.is_shutdown():

        publishWaypoints()
        publishArdronePos()

        # Reset the latch  time
        if actionCode == 0:
            latched = False

        # Take off
        elif actionCode == 1:
            if (not latched):
                latchStartTime = rospy.get_rostime()
                latched = True

            if rospy.get_rostime() < latchStartTime + latchTime:
                pub_takeoff.publish(takeoff_msg)
                rospy.loginfo("Taking off")
            else:
                command(0, 0, 0, 0, 0, 0)
                actionCode = 0
        # Land
        elif actionCode == 2:
            if currentDroneData.z <=  0.5:

                if (not latched):
                    latchStartTime = rospy.get_rostime()
                    latched = True

                if (rospy.get_rostime() < latchStartTime + latchTime):
                    pub_land.publish(land_msg)
                    rospy.loginfo("Landing...")
                else:
                    actionCode = 0

            else:
                command(0, 0, -1, 0, 0, 0)
                actionCode = 2

        # Reset
        elif actionCode == 3:
            rospy.loginfo("inside state 3...")
            pub_reset.publish(reset_msg)
            actionCode = 0

        # Go to Waypoint
        elif actionCode == 4:
            returnTargetInDrone(targetInMap)
            if not wayPointReached(SYS_DEFS.WAYPOINT_ACCURACY):

                gain = 0.3
                xAct = (targetInDrone.position.x * gain)
                yAct = (targetInDrone.position.y * gain)
                zAct = (targetInDrone.position.z * gain)

                rospy.loginfo("Real Pose X: " + str(realPose.pose.position.x) +
                              " Y: " + str(realPose.pose.position.y) +
                              " Z: " + str(realPose.pose.position.z))
                rospy.loginfo("Acceleration X: " + str(xAct) +
                              " Y: " + str(yAct) +
                              " Z: " + str(zAct))

                rospy.loginfo("Current DD X: " + str(currentDroneData.x) +
                              " Y: " + str(currentDroneData.y) +
                              " Z: " + str(currentDroneData.z))

                rospy.loginfo("Target DD X: " + str(targetInDrone.position.x) +
                              " Y: " + str(targetInDrone.position.y) +
                              " Z: " + str(targetInDrone.position.z))

                command(xAct, yAct, zAct, 0, 0, 0)
            else:
                rospy.loginfo("Waypoint Reached ")
                command(0, 0, 0, 0, 0, 0)
                actionCode = 0


        # Look at waypoint
        elif actionCode == 5:
            rospy.loginfo("inside state 5...")
            returnTargetInDrone(targetInMap)
            gain = 0.5  # Proportional goal
            zRotAct = targetInDrone.orientation.z * gain
            command(0, 0, 0, 0, 0, zRotAct)

        # Get Waypoint
        elif actionCode == 6:
            rospy.loginfo("inside state 6...")
            returnTargetInDrone(targetInMap)
            rospy.loginfo("" + str(targetInMap))

        # Look and Go to waypoint
        elif actionCode == 7:
            returnTargetInDrone(targetInMap)
            if not wayPointReached(SYS_DEFS.WAYPOINT_ACCURACY):
                if (wayPointFaced(SYS_DEFS.ANGLE_ACCURACY)):
                    zRotAct = (targetInDrone.orientation.z * SYS_DEFS.ANGLE_GAIN)
                    xAct = (targetInDrone.position.x * SYS_DEFS.POINT_GAIN)
                    yAct = (targetInDrone.position.y * SYS_DEFS.POINT_GAIN)
                    zAct = (targetInDrone.position.z * SYS_DEFS.POINT_GAIN)
                    rospy.loginfo("Real Pose X: " + str(realPose.pose.position.x) +
                                  " Y: " + str(realPose.pose.position.y) +
                                  " Z: " + str(realPose.pose.position.z))
                    rospy.loginfo("Acceleration X: " + str(xAct) +
                                  " Y: " + str(yAct) +
                                  " Z: " + str(zAct))

                    rospy.loginfo("Current DD X: " + str(currentDroneData.x) +
                                  " Y: " + str(currentDroneData.y) +
                                  " Z: " + str(currentDroneData.z))

                    rospy.loginfo("Target DD X: " + str(targetInDrone.position.x) +
                                  " Y: " + str(targetInDrone.position.y) +
                                  " Z: " + str(targetInDrone.position.z))

                    command(xAct, yAct, zAct, 0, 0, zRotAct)
                else:
                    rospy.loginfo("fixing orientation")
                    zRotAct = targetInDrone.orientation.z *  SYS_DEFS.ANGLE_GAIN
                    command(0, 0, 0, 0, 0, zRotAct)
            else:
                rospy.loginfo("Waypoint Reached ")
                command(0, 0, 0, 0, 0, 0)
                actionCode = 0

        # Follow Flightpath
        elif actionCode == 8:

            global currentWaypointCounterForFlightPath
            targetInMap = droneWaypointsFromXML.getWaypointsCoordinates()
            if droneWaypointsFromXML.extractCoordinatesFromXML(currentWaypointCounterForFlightPath):
                returnTargetInDrone(targetInMap)
                if not wayPointReached(SYS_DEFS.WAYPOINT_ACCURACY):
                    if wayPointFaced(SYS_DEFS.ANGLE_ACCURACY):
                        zRotAct = (targetInDrone.orientation.z  * SYS_DEFS.ANGLE_GAIN)
                        xAct    = (targetInDrone.position.x     * SYS_DEFS.POINT_GAIN)
                        yAct    = (targetInDrone.position.y     * SYS_DEFS.POINT_GAIN)
                        zAct    = (targetInDrone.position.z     * SYS_DEFS.POINT_GAIN)
                        command(xAct, yAct, zAct, 0, 0, zRotAct)

                    else:
                        rospy.loginfo("fixing orientation")
                        zRotAct = targetInDrone.orientation.z * SYS_DEFS.ANGLE_GAIN
                        command(0, 0, 0, 0, 0, zRotAct)
                else:
                    rospy.loginfo("Target DD X: " + str(targetInMap.position.x) +
                                  " Y: " + str(targetInMap.position.y) +
                                  " Z: " + str(targetInMap.position.z))
                    currentWaypointCounterForFlightPath +=  1
                    rospy.loginfo("Waypoint Reached " + str(currentWaypointCounterForFlightPath))

            else:
                rospy.loginfo("XML waypoints finished")
                currentWaypointCounterForFlightPath = 0
                command(0, 0, 0, 0, 0, 0)
                actionCode = 0


        # Follow Flightpath for DWM1001
        elif actionCode == 9:

            global currentWaypointCounterForFlightPathDWM1001
            targetInMap = gazeboDwm1001.getAnchorCoordinates()
            if gazeboDwm1001.anchorsReached(currentWaypointCounterForFlightPathDWM1001):
                returnTargetInDrone(targetInMap)
                if not wayPointReached(SYS_DEFS.WAYPOINT_ACCURACY):
                    if wayPointFaced(SYS_DEFS.ANGLE_ACCURACY):
                        zRotAct = (targetInDrone.orientation.z  * SYS_DEFS.ANGLE_GAIN)
                        xAct    = (targetInDrone.position.x     * SYS_DEFS.POINT_GAIN)
                        yAct    = (targetInDrone.position.y     * SYS_DEFS.POINT_GAIN)
                        zAct    = (targetInDrone.position.z     * SYS_DEFS.POINT_GAIN)
                        command(xAct, yAct, zAct, 0, 0, zRotAct)

                    else:
                        rospy.loginfo("fixing orientation")
                        zRotAct = targetInDrone.orientation.z * SYS_DEFS.ANGLE_GAIN
                        command(0, 0, 0, 0, 0, zRotAct)
                else:
                    rospy.loginfo("Target DD X: " + str(targetInMap.position.x) +
                                  " Y: " + str(targetInMap.position.y) +
                                  " Z: " + str(targetInMap.position.z))
                    currentWaypointCounterForFlightPathDWM1001 +=  1
                    rospy.loginfo("Waypoint Reached " + str(currentWaypointCounterForFlightPathDWM1001))

            else:
                rospy.loginfo("XML waypoints finished")
                currentWaypointCounterForFlightPathDWM1001 = 0
                command(0, 0, 0, 0, 0, 0)
                actionCode = 0
        #anchorsExist

        pub_cmd_vel.publish(messageTwist)
        rate.sleep()

def setUpTwist( xLinear, yLinear, zLinear, xAngular, yAngular, zAngular):
    """
    Set up and return a message Twist.

    :param xLinear:  Linear velocity x axis (default 0.0)
    :param yLinear:  Linear velocity y axis (default 0.0)
    :param zLinear:  Linear velocity z axis (default 0.0)
    :param xAngular: Angular velocity x axis (default 0.0)
    :param yAngular: Angular velocity y axis (default 0.0)
    :param zAngular: Angular velocity z axis (default 0.0)

    :returns: none

    """

    global messageTwist

    messageTwist.linear.x = xLinear
    messageTwist.linear.y = yLinear
    messageTwist.linear.z = zLinear
    messageTwist.angular.x = xAngular
    messageTwist.angular.y = yAngular
    messageTwist.angular.z = zAngular
    return messageTwist

def command( xLinear, yLinear, zLinear, xAngular, yAngular, zAngular):
    """Form and assign message Twist.

    :argument
    xLinear -- Linear velocity x axis (default 0.0)
    yLinear -- Linear velocity y axis (default 0.0)
    zLinear -- Linear velocity z axis (default 0.0)
    xAngular -- Angular velocity x axis (default 0.0)
    yAngular -- Angular velocity y axis (default 0.0)
    zAngular -- Angular velocity z axis (default 0.0)

    """
    global messageTwist
    messageTwist = setUpTwist(xLinear, yLinear, zLinear, xAngular, yAngular, zAngular)

def realPoseCallBack(realPoseData):
    """Get real position from /ground_truth/state topic

    :argument
    realPoseData -- Pose data from topic

    """
    global realPose

    realPose = realPoseData.pose


def returnTargetInDrone(target):
    """Convert the coordinates of the target in the drone frame

    :argument
    target -- Pose data from target in the Map

    """

    global currentDroneData

    zRot = -(navDataRotZ360 * math.pi / 180)

    # Target XYZ to the Map frame
    xt = target.position.x
    yt = target.position.y
    zt = target.position.z
    xd = currentDroneData.x
    yd = currentDroneData.y
    zd = currentDroneData.z

    # Translation of  position
    targetInDrone.position.x = (math.cos(zRot)) * (xt - xd) - (math.sin(zRot)) * (yt - yd)
    targetInDrone.position.y = (math.sin(zRot)) * (xt - xd) + (math.cos(zRot)) * (yt - yd)
    targetInDrone.position.z = zt - zd
    targetInDrone.orientation.x = 0
    targetInDrone.orientation.y = 0

    # Angle from the Drone X - axis(Roll axis) to the point vector in the drone frame
    if targetInDrone.position.x is not 0:

        # atan2(y,x) is defined as the angle in the Euclidean plane, given 
        # in radians, between the positive x-axis and the ray to the point (x,y) ≠ (0,0).
        # atan2(y,x) returns a single value θ such that −π < θ ≤ π and, for some r > 0,
        targetInDrone.orientation.z = math.atan2(targetInDrone.position.y, targetInDrone.position.x)

    # Precaution not to devide by  zero
    else:
        if targetInDrone.position.y > 0:
            targetInDrone.orientation.z = math.pi / 2

        elif targetInDrone.position.y < 0:
            targetInDrone.orientation.z = -(math.pi) / 2


def navDataCallBack(nav_msg):
    """Read navdata from the arDrone

    :argument nav_msg: NavData data from drone in the gazebo

    """
    
    global firstTimeSamplingData, navDataRotZ360, droneState, battery, navDataRotZ, lastDroneData, realPose

    #  Get the time stamp of drone
    currentDroneData.timeStamp = nav_msg.header.stamp

    droneState = nav_msg.state
    # For future reference get the battery level of the drone
    battery = nav_msg.batteryPercent
    navDataRotZ = nav_msg.rotZ

    # Check if Z rotation is below 0, if it is add 360 degrees to it
    if nav_msg.rotZ < 0:
        navDataRotZ360 = nav_msg.rotZ + 360
    else:
        navDataRotZ360 = nav_msg.rotZ

    # Linear Velocities
    # 1 km/s is 1000 metres per second which is 1000 [m / sec]
    currentDroneData.xVel = nav_msg.vx /SYS_DEFS.LINEAR_VELOCITY_KPS
    currentDroneData.yVel = nav_msg.vy /SYS_DEFS.LINEAR_VELOCITY_KPS
    currentDroneData.zVel = nav_msg.vz /SYS_DEFS.LINEAR_VELOCITY_KPS

    # Linear Accelerations
    # The metre per second squared is the unit of acceleration in the International System of Units (SI)
    # https://en.wikipedia.org/wiki/Metre_per_second_squared [m / s ^ 2]
    # 1 g0 	980.665 	32.1740 	9.80665 	1
    currentDroneData.xAcc = nav_msg.ax * SYS_DEFS.LINEAR_ACCELLERATION_M_PER_SEC
    currentDroneData.yAcc = nav_msg.ay * SYS_DEFS.LINEAR_ACCELLERATION_M_PER_SEC
    currentDroneData.zAcc = nav_msg.az * SYS_DEFS.LINEAR_ACCELLERATION_M_PER_SEC

    # Angular Rotations in Degrees
    currentDroneData.xRot = nav_msg.rotX
    currentDroneData.yRot = nav_msg.rotY
    currentDroneData.zRot = nav_msg.rotZ

    # TODO remove this if statement, only here for testing
    if not firstTimeSamplingData:

        differenceTIme = (currentDroneData.timeStamp - lastDroneData.timeStamp).to_sec()
        # Add 0.02 incase the time is the same
        differenceTIme = differenceTIme + 0.02

        currentDroneData.xRotVel = (currentDroneData.xRot - lastDroneData.xRot)/differenceTIme  # Degrees / Sec
        currentDroneData.yRotVel = (currentDroneData.yRot - lastDroneData.yRot)/differenceTIme  # Degrees / sec
        currentDroneData.zRotVel = (currentDroneData.zRot - lastDroneData.zRot)/differenceTIme  # Degrees / sec

        if poseEstimationMethod == 1:
            currentDroneData.x = realPose.pose.position.x  # meters[m]
            currentDroneData.y = realPose.pose.position.y  # meters[m]
            currentDroneData.z = realPose.pose.position.z  # meters[m]

        elif poseEstimationMethod == 2:
            currentDroneData.x = externalEstimatedPose.pose.position.x  # meters[m]
            currentDroneData.y = externalEstimatedPose.pose.position.y  # meters[m]
            currentDroneData.z = externalEstimatedPose.pose.position.z  # meters[m]

    firstTimeSamplingData = False
    # Assign the currentDroneData to lastDroneData
    lastDroneData = currentDroneData



def wayPointReached(tolerance):
    """Determine if the waypoint is reached with a tolerance level

    Keyword arguments:
    
    """
    global currentDroneData
    if abs(targetInDrone.position.x) < tolerance :
        if abs(targetInDrone.position.y) < tolerance :
            if abs(targetInDrone.position.z) < tolerance:
                return True
    return False


def wayPointFaced(tolerance):
    """Determine if the waypoint  is faced with absolute value and tolerance

    :arguments
    tolerance -- tolerance of the waypoint faced
    
    """
    if ((abs(targetInDrone.orientation.z)) < tolerance):
        return True
    return False


def publishArdronePos():
    """Publish ARDrone position
    
    """
    global realPose

    dronePos = realPose.pose  # meters[m]
    pub_ardrone_get_pose = rospy.Publisher('/aid/ardrone/get_pos/', Pose, queue_size=1)
    pub_ardrone_get_pose.publish(dronePos)


def publishWaypoints():
    """Publish waypoints from xml file 

    """

    waypointPoseFromXML = Pose()
    counter = 0
    for waypoint in droneWaypointsFromXML.getWaypontsCoordinatesInArray():
        counter = counter + 1
        waypointPoseFromXML.position.x = waypoint[0]
        waypointPoseFromXML.position.y = waypoint[1]
        waypointPoseFromXML.position.z = waypoint[2]
        rate.sleep()
        #rospy.loginfo("publioshing waypoint " + str(waypointPoseFromXML))
        pub_waypoint = rospy.Publisher('/aid/waypoint/'+ str(counter), Pose, queue_size=1)
        pub_waypoint.publish(waypointPoseFromXML)

def JoystickCallBack(data):
    """
    Callback for everytime we use the joystick

    :param data: button values from joystick


    """
    global actionCode

    if data.buttons[SYS_DEFS.BUTTON_LAND] == 1:
        rospy.loginfo("Land Button Pressed: " + str(SYS_DEFS.BUTTON_LAND))
        actionCode = 2

    elif data.buttons[SYS_DEFS.BUTTON_TAKEOFF] == 1:
        rospy.loginfo("Take off Button Pressed: " + str(SYS_DEFS.BUTTON_TAKEOFF))
        actionCode = 1

    elif data.buttons[SYS_DEFS.BUTTON_EMERGENCY] == 1:
        rospy.loginfo("Loading waypoints from XML file: " + str(SYS_DEFS.BUTTON_EMERGENCY))
        # load waypoints from xml
        gazeboWaypoints = LoadWaypointsInGazebo()
        gazeboWaypoints.addWaypointsFromXMLToGazebo()


    elif data.buttons[SYS_DEFS.BUTTON_EMERGENCY_BACKUP] == 1:
        rospy.loginfo("loading waypoint from dwm1001: " + str(SYS_DEFS.BUTTON_EMERGENCY_BACKUP))
        # load dwm1001 anchors
        gazeboDwm1001.execute()

    elif data.buttons[SYS_DEFS.BUTTON_HOVER] == 1:
        rospy.loginfo("Hover Button Pressed: " + str(SYS_DEFS.BUTTON_HOVER))
        actionCode = 0
        command(0, 0, 0, 0, 0, 0)

    elif data.buttons[SYS_DEFS.BUTTON_FOLLOW_FLIGHT_PATH_XML] == 1:
        rospy.loginfo("Follow flight path pressed: " + str(SYS_DEFS.BUTTON_FOLLOW_FLIGHT_PATH_XML))
        actionCode = 8

    elif data.buttons[SYS_DEFS.BUTTON_FOLLOW_FLIGHT_PATH_DWM1001] == 1:
        rospy.loginfo("Follow flight path  from dwm1001 pressed: " + str(SYS_DEFS.BUTTON_FOLLOW_FLIGHT_PATH_DWM1001))
        actionCode = 9

    else:
        # controle axes, pitch, roll and yaw
        command(data.axes[SYS_DEFS.AXIS_PITCH] / SYS_DEFS.SCALE_PITCH,
                data.axes[SYS_DEFS.AXIX_ROLL] / SYS_DEFS.SCALE_ROLL,
                data.axes[SYS_DEFS.AXIS_Z] / SYS_DEFS.SCALE_Z ,
                0,
                0 ,
                data.axes[SYS_DEFS.AXIS_YAW] / SYS_DEFS.SCALE_YAW)

        rospy.loginfo("pitch: " + str(data.axes[SYS_DEFS.AXIS_PITCH] / SYS_DEFS.SCALE_PITCH) +
                      " roll: " + str(data.axes[SYS_DEFS.AXIX_ROLL] / SYS_DEFS.SCALE_ROLL) +
                      " yaw: " + str(data.axes[SYS_DEFS.AXIS_YAW] / SYS_DEFS.SCALE_YAW))


def droneGUICallback( config, level):
    """Dynamic configuration to control waypoints 

    :argument config: data passed from GUI
    
    """

    global actionCode, targetInMap

    if config["land"] == True:
        actionCode = 2
        config["land"] = False
        rospy.loginfo("""Reconfigure Request Action code: {land}""".format(**config))

    elif config["take_off"] == True:
        actionCode = 1
        config["take_off"] = False
        rospy.loginfo("""Reconfigure Request Action code: {take_off}""".format(**config))

    elif config["forward"] == True:
        config["forward"] = False
        actionCode = 0
        command(1, 0, 0, 0, 0, 0)
        rospy.loginfo("""Reconfigure Request Action code: {forward}""".format(**config))

    elif config["backward"] == True:
        config["backward"] = False
        actionCode = 0
        command(-1, 0, 0, 0, 0, 0)
        rospy.loginfo("""Reconfigure Request Action code: {backward}""".format(**config))

    elif config["left"] == True:
        config["left"] = False
        actionCode = 0
        command(0, 0.5, 0, 0, 0, 0)
        rospy.loginfo("""Reconfigure Request Action code: {left}""".format(**config))

    elif config["right"] == True:
        config["right"] = False
        actionCode = 0
        command(0, -0.5, 0, 0, 0, 0)
        rospy.loginfo("""Reconfigure Request Action code: {actionCode}""".format(**config))

    elif config["hover"] == True:
        config["hover"] = False
        actionCode = 0
        command(0, 0, 0, 0, 0, 0)
        rospy.loginfo("""Reconfigure Request Action code: {hover}""".format(**config))

    elif config["look_at_waypoint"] == True:
        config["look_at_waypoint"] = False
        targetInMap.position.x = config["targetInMapX"]
        targetInMap.position.y = config["targetInMapY"]
        targetInMap.position.z = config["targetInMapZ"]
        actionCode = 5
        rospy.loginfo("""Reconfigure Request Action code: {look_at_waypoint}""".format(**config))

    elif config["go_to_waypoint"] == True:
        config["go_to_waypoint"] = False
        targetInMap.position.x = config["targetInMapX"]
        targetInMap.position.y = config["targetInMapY"]
        targetInMap.position.z = config["targetInMapZ"]
        actionCode = 4
        rospy.loginfo("""Reconfigure Request Action code: {go_to_waypoint}""".format(**config))

    elif config["look_and_go"] == True:
        config["look_and_go"] = False
        targetInMap.position.x = config["targetInMapX"]
        targetInMap.position.y = config["targetInMapY"]
        targetInMap.position.z = config["targetInMapZ"]
        actionCode = 7
        rospy.loginfo("""Reconfigure Request Action code: {look_and_go}""".format(**config))


    elif config["load_waypoint_gazebo"] == True:
        config["load_waypoint_gazebo"] = False
        # load waypoints from xml
        gazeboWaypoints = LoadWaypointsInGazebo()
        gazeboWaypoints.addWaypointsFromXMLToGazebo()
        rospy.loginfo("""Reconfigure Request : {load_waypoint_gazebo}""".format(**config))

    elif config["load_waypoint_dwm1001"] == True:
        config["load_waypoint_dwm1001"] = False
        # load waypoints from xml
        gazeboWaypoints = LoadWaypointsInGazebo()
        gazeboWaypoints.addWaypointsFromXMLToGazebo()
        rospy.loginfo("""Reconfigure Request : {load_waypoint_dwm1001}""".format(**config))



    elif config["followFlightPath"] == True:
        config["followFlightPath"]= False
        actionCode = 8
        rospy.loginfo("""Reconfigure Request Action code: {actionCode}""".format(**config))

    return config


if __name__ == '__main__':

    try:
        init()
    except rospy.ROSInterruptException:
        pass
