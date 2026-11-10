cmake_minimum_required(VERSION 3.10)
project(bt_construct)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(wall_e_interfaces REQUIRED)

add_library(skill_nodes src/skill_nodes.cpp)
target_include_directories(skill_nodes PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(skill_nodes PUBLIC
  rclcpp::rclcpp rclcpp_action::rclcpp_action behaviortree_cpp::behaviortree_cpp
  ${geometry_msgs_TARGETS} ${wall_e_interfaces_TARGETS})

add_executable(run_tree src/run_tree.cpp)
target_link_libraries(run_tree skill_nodes)

install(TARGETS skill_nodes run_tree
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY trees DESTINATION share/${PROJECT_NAME})

ament_package()
