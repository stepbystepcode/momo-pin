#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title 墨墨今日未记住
# @raycast.mode silent

# Optional parameters:
# @raycast.icon 📖
# @raycast.packageName 墨墨
# @raycast.description 把今天没记住的单词和墨墨释义贴到屏幕右下角

@PYTHON@ @ROOT@/pin_today.py
