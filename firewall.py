#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import tempfile
import yaml
from jinja2 import Template, Environment, FileSystemLoader

RULES_V4 = "rules.v4"
RULES_V6 = "rules.v6"
PRE_RULES = "pre-rules.sh"
VARS_FILE = "vars.yml"


def load_vars(file):
    if not os.path.exists(file):
        print(f"{file} not found. Ignoring.")
        return {}
    try:
        with open(file) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading vars file: {e}")
        sys.exit(1)


def render_rules(template_file, conf_dir, vars):
    template_path = os.path.join(conf_dir, template_file)
    try:
        env = Environment(loader=FileSystemLoader(conf_dir))
        template = env.get_template(template_file)
        return template.render(**vars)
    except Exception as e:
        sys.stderr.write(f"Error rendering {template_path}: {type(e).__name__}: {e}\n")
        sys.exit(1)


def validate_firewall(rendered_v4, rendered_v6):
    with tempfile.NamedTemporaryFile(mode='w') as v4_tmp, \
            tempfile.NamedTemporaryFile(mode='w') as v6_tmp:

        v4_tmp.write(rendered_v4)
        v6_tmp.write(rendered_v6)
        v4_tmp.flush()
        v6_tmp.flush()

        v4_result = subprocess.run(['iptables-restore', '-t', v4_tmp.name], capture_output=True)
        if v4_result.returncode != 0:
            print(f"IPv4 rules contain errors: {v4_result.stderr.decode()}")
            return False

        v6_result = subprocess.run(['ip6tables-restore', '-t', v6_tmp.name], capture_output=True)
        if v6_result.returncode != 0:
            print(f"IPv6 rules contain errors: {v6_result.stderr.decode()}")
            return False

        print("Rules validation successful")
        return True


def start_firewall(rendered_v4, rendered_v6, pre_rules):
    if not validate_firewall(rendered_v4, rendered_v6):
        sys.exit(1)

    if os.path.isfile(pre_rules):
        if not os.access(pre_rules, os.X_OK):
            print(f"{pre_rules} is not executable. Ignoring.")
        else:
            result = subprocess.run([pre_rules], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Execution of {pre_rules} failed with code {result.returncode}:\n{result.stdout}, {result.stderr}\nEXIT!")
                sys.exit(2)

    with tempfile.NamedTemporaryFile(mode='w') as v4_tmp, \
            tempfile.NamedTemporaryFile(mode='w') as v6_tmp:

        v4_tmp.write(rendered_v4)
        v6_tmp.write(rendered_v6)
        v4_tmp.flush()
        v6_tmp.flush()

        subprocess.run(['iptables-restore', v4_tmp.name], check=True)
        subprocess.run(['ip6tables-restore', v6_tmp.name], check=True)
        print("Firewall rules loaded successfully")


def stop_firewall():
    commands = [
        ['iptables', '-P', 'INPUT', 'ACCEPT'],
        ['iptables', '-P', 'FORWARD', 'ACCEPT'],
        ['iptables', '-P', 'OUTPUT', 'ACCEPT'],
        ['iptables', '-F'],
        ['ip6tables', '-P', 'INPUT', 'ACCEPT'],
        ['ip6tables', '-P', 'FORWARD', 'ACCEPT'],
        ['ip6tables', '-P', 'OUTPUT', 'ACCEPT'],
        ['ip6tables', '-F']
    ]

    for cmd in commands:
        subprocess.run(cmd, check=True)
    print("Firewall rules cleared and policies set to ACCEPT")


description = [
    'Firewall Management Script',
    f'This script loads iptables rules from CONF_DIR/{RULES_V4} and CONF_DIR/{RULES_V6}.',
    f'Before loading rules CONF_DIR/{PRE_RULES} is executed.',
    f'Rules files support Jinja with variables defined in {VARS_FILE}.',
    'Start, stop and restart is aborted if rule validation fails.',
    'More information https://github.com/thorstenkramm/bridged-firewall'
]


def main():
    parser = argparse.ArgumentParser(description=" ".join(description))
    parser.add_argument('--conf-dir', default='/etc/firewall',
                        help='Use custom configuration directory rather then default /etc/firewall')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--start', action='store_true', help='Start firewall, includes validation')
    group.add_argument('--stop', action='store_true',
                       help='Stop firewall, delete all rules and set all policies to accept')
    group.add_argument('--validate', action='store_true', help='Validate rules and exit')
    group.add_argument('--render', action='store_true', help='Print rendered rules to the console and exit')
    args = parser.parse_args()
    conf_dir = args.conf_dir

    vars = load_vars(os.path.join(conf_dir, VARS_FILE))
    rendered_v4 = render_rules(RULES_V4, conf_dir, vars)
    rendered_v6 = render_rules(RULES_V6, conf_dir, vars)

    if args.render:
        print("=== IPv4 Rules ===")
        print(rendered_v4)
        print("\n=== IPv6 Rules ===")
        print(rendered_v6)
    elif args.start:
        start_firewall(rendered_v4, rendered_v6, os.path.join(conf_dir,PRE_RULES))
    elif args.stop:
        stop_firewall()
    elif args.validate:
        sys.exit(0 if validate_firewall(rendered_v4, rendered_v6) else 1)


if __name__ == '__main__':
    main()
