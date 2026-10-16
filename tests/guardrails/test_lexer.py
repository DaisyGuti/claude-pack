"""The shell lexer on its own: what counts as a command, a word and a substitution."""

from __future__ import annotations


def cmds(g, text):
    return [[w.text for w in item.words] for item in g.parse(text) if isinstance(item, g.Command)]


def test_separators_split_commands(g):
    assert cmds(g, "a; b && c || d & e\nf") == [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]


def test_pipe_keeps_stages_in_one_pipeline(g):
    items = [i for i in g.parse("a | b | c; d") if isinstance(i, g.Command)]
    assert [(i.pipeline, i.pos) for i in items] == [(items[0].pipeline, 0)] * 1 + [
        (items[0].pipeline, 1),
        (items[0].pipeline, 2),
        (items[3].pipeline, 0),
    ]
    assert items[0].pipeline != items[3].pipeline


def test_quotes_and_escapes(g):
    assert cmds(g, "echo 'a b' \"c d\" e\\ f") == [["echo", "a b", "c d", "e f"]]
    assert cmds(g, 'echo "a \\" b"') == [["echo", 'a " b']]
    assert cmds(g, "echo ''") == [["echo", ""]]
    assert cmds(g, 'echo "" x') == [["echo", "", "x"]]
    assert cmds(g, "g'i't") == [["git"]]


def test_operators_inside_quotes_are_text(g):
    assert cmds(g, "echo 'a; b && c | d'") == [["echo", "a; b && c | d"]]
    assert cmds(g, 'echo "a ; b"') == [["echo", "a ; b"]]


def test_ansi_c_quoting_is_decoded(g):
    assert cmds(g, "echo $'\\x2d\\x66' $'a\\tb'") == [["echo", "-f", "a\tb"]]


def test_line_continuation_joins_lines(g):
    assert cmds(g, "git push \\\n  origin main") == [["git", "push", "origin", "main"]]


def test_comments_are_dropped_but_hash_inside_a_word_is_kept(g):
    assert cmds(g, "echo a # git push origin main\necho b#c") == [["echo", "a"], ["echo", "b#c"]]


def test_assignments_before_the_command_are_split_off(g):
    items = [i for i in g.parse("A=1 B='x y' cmd C=3") if isinstance(i, g.Command)]
    assert [(n, w.text) for n, w in items[0].assigns] == [("A", "1"), ("B", "x y")]
    assert [w.text for w in items[0].words] == ["cmd", "C=3"]


def test_keywords_are_skipped_at_command_position(g):
    assert cmds(g, "if true; then git push; fi") == [["true"], ["git", "push"]]
    assert cmds(g, "while read l; do echo $l; done") == [["read", "l"], ["echo", "$l"]]


def test_redirects_are_not_arguments(g):
    items = [i for i in g.parse("cmd a >out 2>&1 <in") if isinstance(i, g.Command)]
    assert [w.text for w in items[0].words] == ["cmd", "a"]
    assert [(op, w.text) for op, w in items[0].redirects] == [
        (">", "out"),
        (">&", "1"),
        ("<", "in"),
    ]


def test_command_and_process_substitutions_are_collected(g):
    items = [i for i in g.parse('x "$(a b)" `c d` <(e f) $(g $(h))') if isinstance(i, g.Command)]
    words = items[0].words
    assert [w.subs for w in words[1:]] == [["a b"], ["c d"], ["e f"], ["g $(h)"]]
    assert words[3].procsub and not words[1].procsub


def test_arithmetic_is_not_a_command(g):
    items = g.parse("echo $((1 + 2)) done")
    assert len(items) == 1  # no stray ")" marker is left behind
    assert [w.text for w in items[0].words] == ["echo", "$((1 + 2))", "done"]
    assert items[0].words[1].subs == []


def test_heredoc_body_is_data_and_attached_to_its_command(g):
    items = [
        i
        for i in g.parse("cat <<'EOF' > f\ngit push origin main\nEOF\necho after")
        if isinstance(i, g.Command)
    ]
    assert [[w.text for w in i.words] for i in items] == [["cat"], ["echo", "after"]]
    assert items[0].heredocs == ["git push origin main\n"]


def test_heredoc_with_tab_stripping_and_two_heredocs(g):
    text = "cat <<-A <<B\n\tone\n\tA\ntwo\nB\nnext"
    items = [i for i in g.parse(text) if isinstance(i, g.Command)]
    assert [[w.text for w in i.words] for i in items] == [["cat"], ["next"]]
    assert len(items[0].heredocs) == 2


def test_apostrophes_inside_a_heredoc_in_a_substitution_do_not_swallow_the_rest(g):
    text = "git commit -m \"$(cat <<'EOF'\ndon't (stop)\nEOF\n)\" && git push origin main"
    assert cmds(g, text)[-1] == ["git", "push", "origin", "main"]


def test_unterminated_constructs_end_at_the_end_of_the_text(g):
    assert cmds(g, "echo 'abc") == [["echo", "abc"]]
    assert cmds(g, 'echo "abc') == [["echo", "abc"]]
    assert cmds(g, "echo $(abc") == [["echo", "$(abc"]]
    assert cmds(g, "echo `abc") == [["echo", "`abc`"]]
    assert cmds(g, "") == []
    assert cmds(g, "   \n\n  ") == []


def test_subshell_markers(g):
    kinds = [i if isinstance(i, str) else "cmd" for i in g.parse("(a; b); c")]
    assert kinds == ["(", "cmd", "cmd", ")", "cmd"]


def test_wrappers_are_stripped(g):
    def argv(text):
        item = next(i for i in g.parse(text) if isinstance(i, g.Command))
        env, words = g.unwrap(item.words)
        return env, [w.text for w in words]

    assert argv("sudo -u root -E git push") == ([], ["git", "push"])
    assert argv("env FOO=1 -i BAR=2 git push") == (["FOO=1", "BAR=2"], ["git", "push"])
    assert argv("timeout 5 git push") == ([], ["git", "push"])
    assert argv("nohup nice -n 10 git push") == ([], ["git", "push"])
    assert argv("xargs -I{} git push") == ([], ["git", "push"])
    assert argv("git push") == ([], ["git", "push"])
