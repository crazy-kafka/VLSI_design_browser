import re


class CompiledRe:

    __NAME__ = r'[_a-zA-Z0-9/\\]+'
    __INTEGER__ = r'[0-9]+'
    __BINARY__ = r'[0-9]+\'b[01]+'
    re_binary = re.compile(__BINARY__)

    __MODULE__ = r'module.*?endmodule'
    re_module = re.compile(__MODULE__)

    __MODULE_NAME__ = r'(?P<module_name>[^\s;]+)'
    re_module_name = re.compile(rf'module\s+{__MODULE_NAME__}\s+')

    __PORTS__ = r'(?P<ports>[^;]+)'
    __MODULE_DECLARE__ = rf'module\s+{__MODULE_NAME__}\s*\({__PORTS__}?\)'
    re_module_declare = re.compile(__MODULE_DECLARE__)

    __BITS__ = rf'\[\s*(?P<l_bit>{__INTEGER__})\s*(?::\s*(?P<r_bit>{__INTEGER__}\s*))?\]'
    
    __PORTS_DIRECTION__ = r'(?P<direction>input|inout|output)'
    __PORT_DECLARE__ = rf'(?:\s*{__PORTS_DIRECTION__})\s+(?:{__BITS__}\s+)?(?P<ports_name>[^;:]+)'
    re_port_declare = re.compile(__PORT_DECLARE__)

    __NET_DECLARE__ = rf'wire\s+(?:{__BITS__}\s+)?(?P<net_name>.+)'
    re_net_declare = re.compile(__NET_DECLARE__)

    __INSTANTIATE__ = rf'(?P<ref_name>{__NAME__})\s+(?P<inst_name>{__NAME__})\s*\((?P<pin_conn>[^;]+)?\)'
    re_instantiate = re.compile(__INSTANTIATE__)

    __NET__ = rf'(?P<base_name>{__NAME__})(?:{__BITS__})?$'
    re_net = re.compile(__NET__)
    __PIN_NET_CONN__ = rf'\.(?P<term_name>[^\s\(\)\.]+)\(\s*(?P<net_by_name>.*?)\s*\)'
    re_pin_net_conn = re.compile(__PIN_NET_CONN__)
    __ASSIGN__ = rf'assign\s+(?P<lvalue>[^\s]+)\s*=\s*(?P<rvalue>[^\s]+)'
    re_assign_declare = re.compile(__ASSIGN__)








