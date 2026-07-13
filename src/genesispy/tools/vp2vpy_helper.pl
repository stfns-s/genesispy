#!/usr/bin/env perl
# PPI-backed Perl-snippet to JSON-AST helper.
#
# Protocol (length-prefixed frames on stdin/stdout):
#   request:  "<n>\n<n bytes UTF-8 Perl source>"
#   response: "<m>\n<m bytes UTF-8 JSON>"
# JSON shape:
#   { "ok": true,  "tree": <node> }     on success
#   { "ok": false, "error": "..."  }    on parse failure
# Node shape:
#   { "t": "<short class>", "c": [...] }    for nodes (PPI::Node subclasses)
#   { "t": "<short class>", "v": "..."  }   for tokens (significant ones)
# Insignificant whitespace tokens are dropped. Comment tokens are kept.

use strict;
use warnings;
use PPI;
use JSON::PP;

# Raw handles: the framing protocol counts bytes on both sides (the Python
# peer frames strictly in bytes). UTF-8 decode/encode happens exactly once,
# in read_frame / write_frame.
binmode STDIN,  ':raw';
binmode STDOUT, ':raw';
$| = 1;

my $JSON = JSON::PP->new->utf8(0)->allow_nonref(1);

sub short_class {
    my $cls = shift;
    $cls =~ s/^PPI:://;
    return $cls;
}

sub node_to_hash {
    my $n = shift;
    my $t = short_class(ref $n);

    if ($n->isa('PPI::Node')) {
        my @children;
        for my $c ($n->children) {
            # Drop insignificant whitespace; keep comments and everything else.
            next if $c->isa('PPI::Token::Whitespace');
            push @children, node_to_hash($c);
        }
        return { t => $t, c => \@children };
    }
    # Token leaf.
    return { t => $t, v => $n->content };
}

sub parse_one {
    my $src = shift;
    my $doc = eval { PPI::Document->new(\$src) };
    if (!$doc) {
        my $err = $@ || 'PPI returned undef';
        return { ok => JSON::PP::false, error => "$err" };
    }
    my $tree = eval { node_to_hash($doc) };
    if ($@) {
        return { ok => JSON::PP::false, error => "walk failed: $@" };
    }
    return { ok => JSON::PP::true, tree => $tree };
}

sub read_frame {
    my ($fh) = @_;
    my $hdr = <$fh>;
    return undef unless defined $hdr;
    chomp $hdr;
    return undef if $hdr eq '';
    my $n = int $hdr;    # byte count, as framed by the Python side
    return '' if $n == 0;
    my $buf = '';
    while (length($buf) < $n) {    # raw handle: length() counts bytes
        my $r = read($fh, $buf, $n - length($buf), length($buf));
        last if !defined $r || $r == 0;
    }
    # Payload is UTF-8 bytes; decode in place so PPI sees characters. On
    # invalid UTF-8, utf8::decode leaves $buf as bytes -- PPI still parses
    # and the helper still answers, so no hang either way.
    utf8::decode($buf);
    return $buf;
}

sub write_frame {
    my ($payload) = @_;
    # Encode exactly once: JSON::PP with ``->utf8(0)`` returns a character
    # string; STDOUT is :raw, so we produce the bytes and count them here.
    my $bytes = $payload;
    utf8::encode($bytes) if utf8::is_utf8($bytes);
    print length($bytes), "\n", $bytes;
}

# Allow one-shot CLI invocation: `perl vp2vpy_helper.pl --once <<<'perl'`
if (@ARGV && $ARGV[0] eq '--once') {
    my $src = do { local $/; <STDIN> };
    utf8::decode($src) if defined $src;
    my $out = $JSON->encode(parse_one($src // ''));
    utf8::encode($out) if utf8::is_utf8($out);
    print $out;
    exit 0;
}

# Streaming loop.
while (defined(my $src = read_frame(\*STDIN))) {
    my $resp = parse_one($src);
    write_frame($JSON->encode($resp));
}
