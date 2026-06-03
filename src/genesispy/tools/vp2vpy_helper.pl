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

binmode STDIN,  ':encoding(UTF-8)';
binmode STDOUT, ':encoding(UTF-8)';
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
    my $fh = shift;
    my $hdr = <$fh>;
    return undef unless defined $hdr;
    chomp $hdr;
    return undef if $hdr eq '';
    my $n = int $hdr;
    return '' if $n == 0;
    my $buf = '';
    while (length($buf) < $n) {
        my $r = read($fh, $buf, $n - length($buf), length($buf));
        last if !defined $r || $r == 0;
    }
    return $buf;
}

sub write_frame {
    my $payload = shift;
    # Frame the response in bytes (not characters): the Python reader pulls
    # exactly the byte count we announce, then decodes UTF-8 on its side.
    # JSON::PP with ``->utf8(0)`` returns a Perl string; encode to bytes
    # only if it's still flagged as a character string.
    my $bytes = $payload;
    utf8::encode($bytes) if utf8::is_utf8($bytes);
    print length($bytes), "\n", $bytes;
}

# Allow one-shot CLI invocation: `perl vp2vpy_helper.pl --once <<<'perl'`
if (@ARGV && $ARGV[0] eq '--once') {
    my $src = do { local $/; <STDIN> };
    print $JSON->encode(parse_one($src // ''));
    exit 0;
}

# Streaming loop.
while (defined(my $src = read_frame(\*STDIN))) {
    my $resp = parse_one($src);
    write_frame($JSON->encode($resp));
}
