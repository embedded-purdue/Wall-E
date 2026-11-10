// Wall-E's skills as behavior tree nodes, using the names and ports in
// behavior_tree/bt_construct/wall_e.yaml (schema v1).
//
// Implemented so far: SearchFor, NavigateTo, Grab, Crush (actions) and
// IsVisible (condition). Say, Express, LookAt, MoveArm, Release and IsAt
// follow the same pattern and are next.
//
// Blackboard convention (schema.md): SearchFor("can") and IsVisible("can")
// write "can.location"; NavigateTo("can") and Grab("can") read it.

#pragma once

#include <string>

#include <behaviortree_cpp/bt_factory.h>
#include <geometry_msgs/msg/point_stamped.hpp>
#include <rclcpp/rclcpp.hpp>

namespace bt_construct {

// "can" -> "can.location"
std::string locationKey(const std::string& name);

// The location stored for `name`, or an empty PointStamped (frame_id == "")
// if nothing has been found yet. The skills read an empty frame_id as
// "not given" and fall back to a known spot.
geometry_msgs::msg::PointStamped lookupLocation(const BT::Blackboard& blackboard,
                                                const std::string& name);

// Registers every implemented skill node with the factory. Their ROS
// clients live on `node`, which must be spun by an executor on another
// thread while the tree runs.
void registerSkillNodes(BT::BehaviorTreeFactory& factory, rclcpp::Node::SharedPtr node);

}  // namespace bt_construct
