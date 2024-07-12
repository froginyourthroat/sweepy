#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
import numpy as np
import cv2
from cv_bridge import CvBridge, CvBridgeError
#import logging
import threading

class ObstacleDetectionNode(Node):
    def __init__(self):
        super().__init__('obstacle_detection_node')
        self.bridge = CvBridge()
        self.create_subscription(Image, '/camera/realsense2_camera/depth/image_rect_raw', self.depth_callback, 10)
        self.pub_cmd_vel = self.create_publisher(Twist, 'cmd_vel', 10)

        # Set up logging
        #logging.basicConfig(filename='robot_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')
        #self.logger = logging.getLogger()

        # Set up periodic timer for obstacles
        self.obstacle_check_timer = self.create_timer(0.5, self.check_for_obstacles)

        # Placeholder for the latest depth image
        self.latest_depth_image = None

        # Thread to handle image display
        self.display_thread = threading.Thread(target=self.display_images)
        self.display_thread.daemon = True
        self.display_thread.start()

        # Placeholder for the previous command 
        self.prev_cmd = Twist()

        # Flags to indicate obstacle detection
        self.obstacle_left = False
        self.obstacle_right = False
        self.turning = False

    def depth_callback(self, msg):
        try:
            # Convert ROS Image message to OpenCV image
            self.latest_depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except CvBridgeError as e:
            self.get_logger().error(f'CvBridge Error: {e}')

    def check_for_obstacles(self):
        if self.latest_depth_image is None:
            return

        # Split the depth image into left and right parts
        height, width = self.latest_depth_image.shape
        left_image = self.latest_depth_image[:, :width//2]
        right_image = self.latest_depth_image[:, width//2:]

        self.obstacle_left = False
        self.obstacle_right = False

        obstacles = {'left': False, 'right': False}

        for region_name, region in {'left': left_image, 'right': right_image}.items():
            valid_region_depths = region[region > 0]
            if valid_region_depths.size > 0:
                min_region_depth = np.min(valid_region_depths)
                if min_region_depth < 500:
                    obstacles[region_name] = True
                    self.get_logger().info(f'Obstacle detected in {region_name} region with depth {min_region_depth} mm.')
        
        if obstacles['left'] and not obstacles['right']:
            self.get_logger().info('Obstacle detected on the left, turning right.')
            self.obstacle_left = True
            self.start_turning('right')
        elif obstacles['right'] and not obstacles['left']:
            self.get_logger().info('Obstacle detected on the right, turning left.')
            self.obstacle_right = True
            self.start_turning('left')
        elif obstacles['left'] and obstacles['right']:
            self.get_logger().info('Obstacles detected on both sides. Stop')
            self.obstacle_left = True
            self.obstacle_right = True
            self.stop()
        else:
            self.get_logger().info('No obstacles detected, moving forward.')
            self.move_forward()

    def move_forward(self):
        cmd = Twist()
        cmd.linear.x = 0.7
        cmd.angular.z = 0.0
        self.pub_cmd_vel.publish(cmd)
        self.get_logger().info('Command: Move Forward')
        self.turning = False

    def turn_left(self):
        cmd = Twist()
        cmd.linear.x = 0.0
        cmd.angular.z = 0.2  # Slow turn
        self.pub_cmd_vel.publish(cmd)
        self.get_logger().info('Command: Turn Left')

    def turn_right(self):
        cmd = Twist()
        cmd.linear.x = 0.0
        cmd.angular.z = -0.2  # Slow turn
        self.pub_cmd_vel.publish(cmd)
        self.get_logger().info('Command: Turn Right')

    def stop(self):
        cmd = Twist()
        cmd.linear.x = 0.0
        cmd.angular.z = 0.0
        self.pub_cmd_vel.publish(cmd)
        self.get_logger().info('Command: Stop')
        self.turning = False

    def start_turning(self, direction):
        self.turning = True
        if direction == 'left':
            self.turn_left()
        elif direction == 'right':
            self.turn_right()

        threading.Timer(0.5, self.check_turning_obstacle).start()

    def check_turning_obstacle(self):
        if self.latest_depth_image is None:
            return

        # Split the depth image into left and right parts
        height, width = self.latest_depth_image.shape
        left_image = self.latest_depth_image[:, :width//2]
        right_image = self.latest_depth_image[:, width//2:]

        obstacles = {'left': False, 'right': False}

        for region_name, region in {'left': left_image, 'right': right_image}.items():
            valid_region_depths = region[region > 0]
            if valid_region_depths.size > 0:
                min_region_depth = np.min(valid_region_depths)
                if min_region_depth < 500:
                    obstacles[region_name] = True

        if not obstacles['left'] and not obstacles['right']:
            self.move_forward()
        else:
            if self.obstacle_left:
                self.start_turning('right')
            elif self.obstacle_right:
                self.start_turning('left')

    def publish_cmd(self, cmd):
        if cmd.linear.x != self.prev_cmd.linear.x or cmd.angular.z != self.prev_cmd.angular.z:
            self.prev_cmd = cmd 
            self.pub_cmd_vel.publish(cmd)

    def display_images(self):
        while True:
            if self.latest_depth_image is None:
                continue

            height, width = self.latest_depth_image.shape
            left_image = self.latest_depth_image[:, :width//2]
            right_image = self.latest_depth_image[:, width//2:]
            left_normalized = cv2.normalize(left_image, None, 0, 255, cv2.NORM_MINMAX)

            left_normalized = np.uint8(left_normalized)
            left_colormap = cv2.applyColorMap(left_normalized, cv2.COLORMAP_JET)

            right_normalized = cv2.normalize(right_image, None, 0, 255, cv2.NORM_MINMAX)
            right_normalized = np.uint8(right_normalized)
            right_colormap = cv2.applyColorMap(right_normalized, cv2.COLORMAP_JET)

            if self.obstacle_left:
                cv2.putText(left_colormap, 'Obstacle', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
            if self.obstacle_right:
                cv2.putText(right_colormap, 'Obstacle', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)

            cv2.imshow('Left Depth Image', left_colormap)
            cv2.imshow('Right Depth Image', right_colormap)
            cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = ObstacleDetectionNode()
    rclpy.spin(node)
    rclpy.shutdown()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
