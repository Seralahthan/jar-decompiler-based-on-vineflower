package com.test.java11;

import java.util.List;
import java.util.stream.Collectors;

public class VarDemo {
    public String processText(String input) {
        var trimmed = input.strip();
        var lines = trimmed.lines().collect(Collectors.toList());
        var repeated = "ha".repeat(3);
        var blank = "  ".isBlank();
        return trimmed + lines.size() + repeated + blank;
    }
}
