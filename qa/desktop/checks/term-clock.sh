#!/bin/bash
# A clock ticking once a second in the top-left corner of the terminal, as the only change.
# The speed check uses it to see that glass far from a change does not redraw for it.
printf '\e]0;LGQA clock\a\e[?25l\e[2J'
while :; do printf '\e[2;2H%s' "$(date +%T)"; sleep 1; done
