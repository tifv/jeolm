cmake_minimum_required(VERSION 2.8)
project(jeolm NONE)

subdirs(latex)

find_program(PYTHON3
    NAMES python3.4 python3
)

install(CODE "
execute_process(
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    COMMAND ${PYTHON3} setup.py install
)")

