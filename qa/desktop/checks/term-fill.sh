#!/bin/bash
# Paints the whole terminal green with a dark tag in the top-left corner, and again after
# every resize. The release checks use it to see leftovers and content that drifts.
paint() { printf '\e[?25l\e[48;2;0;200;80m\e[2J\e[H\e[48;2;16;16;16m%s\e[48;2;0;200;80m' '                '; }
trap paint WINCH
paint
while :; do sleep 0.2; done
