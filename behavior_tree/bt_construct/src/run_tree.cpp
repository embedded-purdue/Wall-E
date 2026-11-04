// Loads a behavior tree XML file and runs it against the skills.
//
//   ros2 run bt_construct run_tree <tree.xml> [--tick-ms 100]
//
// Exits 0 if the tree succeeds, 1 if it fails, 2 on bad input. Ctrl-C halts
// the tree first, which cancels whatever skill is running, then exits.

#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <string>
#include <thread>

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/loggers/bt_cout_logger.h>
#include <rclcpp/rclcpp.hpp>

#include "bt_construct/skill_nodes.hpp"

namespace {

std::atomic<bool> g_interrupted{false};

void onSigint(int) { g_interrupted = true; }

int usage() {
  std::cerr << "usage: run_tree <tree.xml> [--tick-ms N]\n";
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  // We handle SIGINT ourselves: rclcpp's default handler would shut the
  // context down before we get a chance to cancel the running goal.
  rclcpp::init(argc, argv, rclcpp::InitOptions(), rclcpp::SignalHandlerOptions::None);
  std::signal(SIGINT, onSigint);

  const auto args = rclcpp::remove_ros_arguments(argc, argv);
  if (args.size() < 2) return usage();
  const std::string tree_file = args[1];
  int tick_ms = 100;
  for (size_t i = 2; i + 1 < args.size(); i += 2) {
    if (args[i] == "--tick-ms") tick_ms = std::stoi(args[i + 1]);
    else return usage();
  }

  auto node = std::make_shared<rclcpp::Node>("bt_runner");
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  std::thread spinner([&executor] { executor.spin(); });

  BT::BehaviorTreeFactory factory;
  bt_construct::registerSkillNodes(factory, node);

  int exit_code = 1;
  try {
    BT::Tree tree = factory.createTreeFromFile(tree_file);
    BT::StdCoutLogger transitions(tree);  // prints every node's status change

    BT::NodeStatus status = BT::NodeStatus::RUNNING;
    const auto period = std::chrono::milliseconds(tick_ms);
    while (status == BT::NodeStatus::RUNNING && !g_interrupted) {
      status = tree.tickOnce();
      if (status == BT::NodeStatus::RUNNING) tree.sleep(period);
    }

    if (g_interrupted) {
      tree.haltTree();
      std::this_thread::sleep_for(std::chrono::milliseconds(200));  // let the cancel go out
      std::cout << "interrupted: tree halted\n";
    } else {
      std::cout << "tree finished: " << BT::toStr(status) << "\n";
      exit_code = status == BT::NodeStatus::SUCCESS ? 0 : 1;
    }
  } catch (const std::exception& e) {
    // Most often: the tree uses a node that isn't implemented yet.
    std::cerr << "could not load " << tree_file << ": " << e.what() << "\n";
    exit_code = 2;
  }

  executor.cancel();
  spinner.join();
  rclcpp::shutdown();
  return exit_code;
}
