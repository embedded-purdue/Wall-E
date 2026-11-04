#include "bt_construct/skill_nodes.hpp"

#include <chrono>
#include <future>
#include <memory>

#include <behaviortree_cpp/condition_node.h>
#include <wall_e_interfaces/action/crush.hpp>
#include <wall_e_interfaces/action/grab.hpp>
#include <wall_e_interfaces/action/navigate_to.hpp>
#include <wall_e_interfaces/action/search_for.hpp>
#include <wall_e_interfaces/srv/is_visible.hpp>

#include "bt_construct/skill_action.hpp"

namespace bt_construct {

namespace action = wall_e_interfaces::action;
namespace srv = wall_e_interfaces::srv;
using geometry_msgs::msg::PointStamped;

std::string locationKey(const std::string& name) { return name + ".location"; }

PointStamped lookupLocation(const BT::Blackboard& blackboard, const std::string& name) {
  PointStamped location;
  if (!blackboard.get(locationKey(name), location)) {
    return PointStamped{};  // frame_id "" means "not known"
  }
  return location;
}

namespace {

// Reads a required string port. Logs and returns false if it is missing or empty.
bool requireString(const BT::TreeNode& node, const rclcpp::Logger& logger,
                   const std::string& port, std::string& out) {
  auto value = node.getInput<std::string>(port);
  if (!value || value->empty()) {
    RCLCPP_ERROR(logger, "%s: missing required port '%s'", node.name().c_str(), port.c_str());
    return false;
  }
  out = *value;
  return true;
}

// ---- Actions ---------------------------------------------------------------

class SearchFor : public SkillAction<action::SearchFor> {
 public:
  using SkillAction::SkillAction;

  static BT::PortsList providedPorts() {
    return {BT::InputPort<std::string>("object"), BT::InputPort<std::string>("hint", "", "")};
  }

 protected:
  bool makeGoal(Goal& goal) override {
    if (!requireString(*this, logger(), "object", goal.object)) return false;
    goal.hint = getInput<std::string>("hint").value_or("");
    object_ = goal.object;
    return true;
  }

  void onSuccess(const Result& result) override {
    config().blackboard->set(locationKey(object_), result.location);
  }

 private:
  std::string object_;
};

class NavigateTo : public SkillAction<action::NavigateTo> {
 public:
  using SkillAction::SkillAction;

  static BT::PortsList providedPorts() { return {BT::InputPort<std::string>("target")}; }

 protected:
  bool makeGoal(Goal& goal) override {
    if (!requireString(*this, logger(), "target", goal.target)) return false;
    goal.location = lookupLocation(*config().blackboard, goal.target);
    return true;
  }
};

class Grab : public SkillAction<action::Grab> {
 public:
  using SkillAction::SkillAction;

  static BT::PortsList providedPorts() { return {BT::InputPort<std::string>("object")}; }

 protected:
  bool makeGoal(Goal& goal) override {
    if (!requireString(*this, logger(), "object", goal.object)) return false;
    goal.location = lookupLocation(*config().blackboard, goal.object);
    return true;
  }
};

class Crush : public SkillAction<action::Crush> {
 public:
  using SkillAction::SkillAction;

  static BT::PortsList providedPorts() { return {BT::InputPort<std::string>("object")}; }

 protected:
  bool makeGoal(Goal& goal) override {
    return requireString(*this, logger(), "object", goal.object);
  }
};

// ---- Conditions ------------------------------------------------------------

// Conditions must answer within the tick (never RUNNING), so this blocks on
// the service for at most kTimeout. The executor thread delivers the response.
class IsVisible : public BT::ConditionNode {
 public:
  IsVisible(const std::string& name, const BT::NodeConfig& config,
            rclcpp::Node::SharedPtr node, const std::string& service_name)
      : BT::ConditionNode(name, config),
        node_(std::move(node)),
        client_(node_->create_client<srv::IsVisible>(service_name)) {}

  static BT::PortsList providedPorts() { return {BT::InputPort<std::string>("object")}; }

  BT::NodeStatus tick() override {
    auto request = std::make_shared<srv::IsVisible::Request>();
    if (!requireString(*this, node_->get_logger(), "object", request->object)) {
      return BT::NodeStatus::FAILURE;
    }
    if (!client_->wait_for_service(kTimeout)) {
      RCLCPP_ERROR(node_->get_logger(), "%s: service %s not available", name().c_str(),
                   client_->get_service_name());
      return BT::NodeStatus::FAILURE;
    }
    auto future = client_->async_send_request(request);
    if (future.wait_for(kTimeout) != std::future_status::ready) {
      client_->remove_pending_request(future);
      RCLCPP_WARN(node_->get_logger(), "%s: no answer within %ld ms", name().c_str(),
                  static_cast<long>(kTimeout.count()));
      return BT::NodeStatus::FAILURE;
    }
    auto response = future.get();
    if (!response->visible) return BT::NodeStatus::FAILURE;
    config().blackboard->set(locationKey(request->object), response->location);
    return BT::NodeStatus::SUCCESS;
  }

 private:
  static constexpr std::chrono::milliseconds kTimeout{1000};
  rclcpp::Node::SharedPtr node_;
  rclcpp::Client<srv::IsVisible>::SharedPtr client_;
};

// Registers NodeT under `id`, constructed with the shared ROS node and the
// skill's action or service name.
template <class NodeT>
void registerSkill(BT::BehaviorTreeFactory& factory, const std::string& id,
                   rclcpp::Node::SharedPtr node, const std::string& ros_name) {
  factory.registerBuilder<NodeT>(
      id, [node, ros_name](const std::string& name, const BT::NodeConfig& config) {
        return std::make_unique<NodeT>(name, config, node, ros_name);
      });
}

}  // namespace

void registerSkillNodes(BT::BehaviorTreeFactory& factory, rclcpp::Node::SharedPtr node) {
  registerSkill<SearchFor>(factory, "SearchFor", node, "/skills/search_for");
  registerSkill<NavigateTo>(factory, "NavigateTo", node, "/skills/navigate_to");
  registerSkill<Grab>(factory, "Grab", node, "/skills/grab");
  registerSkill<Crush>(factory, "Crush", node, "/skills/crush");
  registerSkill<IsVisible>(factory, "IsVisible", node, "/skills/is_visible");
}

}  // namespace bt_construct
