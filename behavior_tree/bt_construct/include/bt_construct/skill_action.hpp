// A behavior tree leaf that runs one Wall-E skill through its ROS 2 action.
//
// Lifecycle (BT::StatefulActionNode):
//   onStart()   send the goal, return RUNNING
//   onRunning() called every tick: RUNNING until the result arrives, then
//               SUCCESS if the skill reported success, otherwise FAILURE
//   onHalted()  the tree stopped this branch (Ctrl-C, a Fallback moved on,
//               a reactive condition failed): cancel the goal on the server
//
// The action client's callbacks run on the executor thread, while the tree
// ticks on the main thread, so everything the callbacks touch is behind
// mutex_. Each goal gets a generation number; a late callback from a goal we
// already gave up on sees a different number and is ignored.

#pragma once

#include <chrono>
#include <memory>
#include <mutex>
#include <optional>
#include <string>

#include <behaviortree_cpp/action_node.h>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>

namespace bt_construct {

template <class ActionT>
class SkillAction : public BT::StatefulActionNode {
 public:
  using Goal = typename ActionT::Goal;
  using Result = typename ActionT::Result;
  using GoalHandle = rclcpp_action::ClientGoalHandle<ActionT>;

  SkillAction(const std::string& name, const BT::NodeConfig& config,
              rclcpp::Node::SharedPtr node, const std::string& action_name)
      : BT::StatefulActionNode(name, config),
        node_(std::move(node)),
        action_name_(action_name),
        client_(rclcpp_action::create_client<ActionT>(node_, action_name)) {}

 protected:
  // Fill in the goal from this node's ports. Return false if an input is
  // missing or invalid; the node then fails without contacting the skill.
  virtual bool makeGoal(Goal& goal) = 0;

  // Called once with the result of a successful goal, e.g. to write a found
  // object's location to the blackboard.
  virtual void onSuccess(const Result& /*result*/) {}

  rclcpp::Logger logger() const { return node_->get_logger(); }

  BT::NodeStatus onStart() override {
    if (!client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_ERROR(logger(), "%s: no action server at %s", name().c_str(),
                   action_name_.c_str());
      return BT::NodeStatus::FAILURE;
    }
    Goal goal;
    if (!makeGoal(goal)) {
      return BT::NodeStatus::FAILURE;
    }

    std::lock_guard<std::mutex> lock(mutex_);
    const int gen = ++generation_;
    state_ = State::kWaitingForAccept;
    goal_handle_.reset();
    result_.reset();

    typename rclcpp_action::Client<ActionT>::SendGoalOptions options;
    options.goal_response_callback = [this, gen](typename GoalHandle::SharedPtr handle) {
      std::lock_guard<std::mutex> lock(mutex_);
      if (gen != generation_) return;
      if (!handle) {
        state_ = State::kRejected;
      } else {
        goal_handle_ = handle;
        state_ = State::kRunning;
      }
    };
    options.result_callback = [this, gen](const typename GoalHandle::WrappedResult& wrapped) {
      std::lock_guard<std::mutex> lock(mutex_);
      if (gen != generation_) return;
      result_ = wrapped;
      state_ = State::kDone;
    };
    client_->async_send_goal(goal, options);
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override {
    std::optional<typename GoalHandle::WrappedResult> result;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (state_ == State::kRejected) {
        RCLCPP_WARN(logger(), "%s: goal rejected by %s", name().c_str(), action_name_.c_str());
        return BT::NodeStatus::FAILURE;
      }
      if (state_ != State::kDone) {
        return BT::NodeStatus::RUNNING;
      }
      result = result_;
    }
    // Outside the lock: onSuccess may touch the blackboard.
    const auto& r = result->result;
    if (result->code == rclcpp_action::ResultCode::SUCCEEDED && r && r->success) {
      onSuccess(*r);
      return BT::NodeStatus::SUCCESS;
    }
    RCLCPP_WARN(logger(), "%s failed: %s", name().c_str(),
                r && !r->reason.empty() ? r->reason.c_str() : "no reason given");
    return BT::NodeStatus::FAILURE;
  }

  void onHalted() override {
    typename GoalHandle::SharedPtr handle;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      ++generation_;  // ignore anything that still arrives for this goal
      if (state_ == State::kRunning) handle = goal_handle_;
      state_ = State::kIdle;
    }
    if (handle) {
      RCLCPP_INFO(logger(), "%s: halted, canceling goal", name().c_str());
      client_->async_cancel_goal(handle);
    }
  }

 private:
  enum class State { kIdle, kWaitingForAccept, kRunning, kRejected, kDone };

  rclcpp::Node::SharedPtr node_;
  std::string action_name_;
  typename rclcpp_action::Client<ActionT>::SharedPtr client_;

  std::mutex mutex_;
  int generation_ = 0;
  State state_ = State::kIdle;
  typename GoalHandle::SharedPtr goal_handle_;
  std::optional<typename GoalHandle::WrappedResult> result_;
};

}  // namespace bt_construct
