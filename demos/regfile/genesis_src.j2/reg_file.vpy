/* *****************************************************************************
 * File: reg_file.vpy
 *
 * Description:
 * This file is using Genesis2 to make a register file.
 * A register file have a config bus input port, and a config bus output port.
 * The configuration request values are flopped and than handled:
 * * If cfgIn_op is a no-op, nothing happens.
 * * If cfgIn_op is a bypass op, the  cfgIn_* signals are passed to the
 *      cfgOut_* ports.
 * * If cfgIn_op is a read/write op, and cfgIn_addr is with in the address
 *      range, then the corresponding register is read/written. The values
 *      are streamed to the cfgOut_* ports, except for cfgOut_op that becomes
 *      a bypass-op.
 *      If cfgIn_addr is not in this reg_file address range, all the  cfgIn_*
 *      signals are passed to the cfgOut_* ports. Someone else will answer...
 *
 * Note: All registers in the register file are write-able and readable by the
 *      configuration bus (even though some may only have output ports or only
 *      input ports).
 *
 *
 * REQUIRED GENESIS PARAMETERS:
 * ----------------------------
 * * REG_LIST  - List of registers. Each element in the list is a hash that contains
 *    * name - used for generating the enable and data output/input signals
 *    * width - register width
 *    * default - (optional) default value. Can be set later by XML input
 *    * IEO - I indicates this register connected to an input signal
 *            E indicates that the input is qualified by an enable
 *            O indicates that the output is connected to an output signal
 *            Valid options include: I, IE, O, IO, IEO
 *    * comment - (optional) description of the register
 * * BASE_ADDR - Base address for this module
 * * CFG_OPCODES - Interpretation of the opcode. Must contain the following feilds:
 *    * nop - value of cfgIn_op for a no-op (default is 0)
 *    * read - value of cfgIn_op for a read operation (default is 1)
 *    * write - value of cfgIn_op for a write operation (default is 2)
 *    * bypass - value of cfgIn_op for bypassing the control signals (default is 3)
 * * IFC_REF - An instance of the reg_file_ifc (used as reference)
 *
 * Inputs:
 * -------
 * Clk
 * Reset
 * cfgIn - Incomming config request
 * foreach REG in REG_LIST (but depending on the IEO flag):
 *  * <REG.name>_en - enable signal for the register
 *  * <REG.name>_d - data input for the register
 *
 * Outputs:
 * --------
 * cfgOut - Outgoing reply for config request cfgIn
 * foreach REG in REG_LIST (but depending on the IEO flag):
 *  * <REG.name>_q - data output for the register
 *
 *
 * NOTE: registers with input from the design may become resource contention
 *       if both their private enable and their by-address enable signals are raised.
 *       Priority is always given to data from the cfg bus!
 *
 * ****************************************************************************/

{% # Python imports %}
{% import math %}
{%  %}
{%  %}
// ACTUAL GENESIS2 PARAMETERIZATIONS
{% reg_list = parameter('REG_LIST', [{'name': 'regA', 'width': 5, 'default': 17, 'IEO': 'ie', 'comment': 'this is a reg'}, {'name': 'regB', 'width': 10, 'default': 27, 'IEO': 'o'}, {'name': 'regC', 'width': 15, 'IEO': 'ieo'}, {'name': 'regD', 'width': 13, 'default': 4, 'IEO': 'i'}]) %}
{% num_regs = len(reg_list) %}
{% base_addr = parameter('BASE_ADDR', 0) %}
{% cfg_ops = parameter('CFG_OPCODES', {'nop': 0, 'read': 1, 'write': 2, 'bypass': 3}) %}
{% ifc_ref = parameter('IFC_REF', '') %}
{% if ifc_ref == '': %}
{%     raise ValueError("Missing parameter: IFC_REF") %}
{% endif %}
{%  %}
{% # Extract paramteres from the interdace %}
{% cfgIn_ifc_obj = clone_inst(ifc_ref, 'cfgIn') %}
{% cfgOut_ifc_obj = clone_inst(ifc_ref, 'cfgOut') %}
{% cfg_bus_width = cfgIn_ifc_obj.get_param('CFG_BUS_WIDTH') %}
{% cfg_addr_width = cfgIn_ifc_obj.get_param('CFG_ADDR_WIDTH') %}
{% cfg_op_width = cfgIn_ifc_obj.get_param('CFG_OPCODE_WIDTH') %}
{%  %}
{%  %}
{% # Verify correctness of register parameters: %}
{% cnt = 0 %}
{% for reg in reg_list: %}
{%     if 'name' not in reg: %}
{%         raise ValueError(f"Register {cnt} is missing it's name!") %}
{%     endif %}
{%     if 'width' not in reg: %}
{%         raise ValueError(f"Register {reg['name']} (reg {cnt}) is missing it's width!") %}
{%     endif %}
{%     if reg['width'] > cfg_bus_width: %}
{%         raise ValueError(f"Register {reg['name']} (reg {cnt}) is wider than the config bus!") %}
{%     endif %}
{%     if 'IEO' not in reg: %}
{%         raise ValueError(f"Register {reg['name']} (reg {cnt}) is missing it's IEO!") %}
{%     endif %}
{%     if reg['IEO'].lower() not in ('i', 'ie', 'o', 'io', 'ieo'): %}
{%         raise ValueError(f"Register {reg['name']} (reg {cnt}) has an invalid IEO flag -->{reg['IEO']}<--! (allowed values: I, IE, O, IO, IEO)") %}
{%     endif %}
{%     cnt += 1 %}
{% endfor %}
{%  %}
{% # Verify correctness of opcode parameters: %}
{% if 'nop' not in cfg_ops or 'read' not in cfg_ops or 'write' not in cfg_ops or 'bypass' not in cfg_ops: %}
{%     raise ValueError("CFG_OPCODES must define values for all of {nop, read, write, bypass} opcodes") %}
{% endif %}
{% nop = cfg_ops['nop'] %}
{% rdop = cfg_ops['read'] %}
{% wrop = cfg_ops['write'] %}
{% bypassop = cfg_ops['bypass'] %}
{% if (nop > 2**cfg_op_width-1) or (rdop > 2**cfg_op_width-1) or (wrop > 2**cfg_op_width-1) or (bypassop > 2**cfg_op_width-1): %}
{%     raise ValueError("CFG_OPCODES values don't fit within CFG_OPCODE_WIDTH bits") %}
{% endif %}
{%  %}
{%  %}
{% num_req_addr_bits = math.ceil(math.log(num_regs)/math.log(2)) %}

// Fix for reg files with single registers
{% if num_req_addr_bits == 0: %}
{%     num_req_addr_bits = 1 %}
{% endif %}
{% num_not_used_lsbs = math.ceil(math.log(cfg_bus_width/8)/math.log(2)) %}
{% usable_addr_range = f"{num_req_addr_bits+num_not_used_lsbs-1}:{num_not_used_lsbs}" %}
{% base_addr_range = f"{cfg_addr_width-1}:{num_req_addr_bits+num_not_used_lsbs}" %}
{% base_addr_width = cfg_addr_width - (num_req_addr_bits+num_not_used_lsbs) %}
{% base_addr_trunc = base_addr // 2**(num_req_addr_bits+num_not_used_lsbs) %}
{% base_addr_hex = f"{base_addr_width}'h{base_addr_trunc:x}" %}
{%  %}

// =============================================================================
//                  LIST OF REGISTERS IN THIS MODULE:
// =============================================================================
{% base_addr_legend = f"{base_addr}'h{base_addr:x}" %}
// LEGEND:
//      BASE_ADDRESS {{ base_addr_legend }}
//      IEO:  I for input (register samples design)
//            O for output (register drives design)
//            IE for enabled input (register samples design if enable is high)
//
// REGISTERS
{% cnt = 0 %}
{% for reg in reg_list: %}
// {{ reg['name'] }} [{{ reg['width']-1 }}:0] IEO={{ reg['IEO'] }}
// Offset={{ cnt<<num_not_used_lsbs }} Comment:{{ reg.get('comment','') }}
{%     cnt += 1 %}
{% endfor %}




// =============================================================================
//                             MODULE:
// =============================================================================
module {{ mname }}
  (
   // inputs for the config interface
   {{ cfgIn_ifc_obj.mname }}.cfgIn cfgIn, // incoming requests
   {{ cfgOut_ifc_obj.mname }}.cfgOut cfgOut, // outgoing responds

   {% for reg in reg_list: %}
   {%     if 'i' in reg['IEO'].lower(): %}
    // inputs for register {{ reg['name'] }}
    input [{{ reg['width']-1 }}:0]       {{ reg['name'] }}_d,
   {%     endif %}
   {%     if 'e' in reg['IEO'].lower(): %}
    input                         {{ reg['name'] }}_en,
   {%     endif %}
   {%     if 'i' in reg['IEO'].lower(): %}

   {%     endif %}
   {% endfor %}

   //outputs
   {% for reg in reg_list: %}
   {%     if 'o' in reg['IEO'].lower(): %}
    // outputs for register {{ reg['name'] }}
    output [{{ reg['width']-1 }}:0]       {{ reg['name'] }}_q,

   {%     endif %}
   {% endfor %}

   // Generic inputs
    input 			       Clk,
    input                              Reset
   );


   // floping cfg inputs to produce delayed signals:
   logic [{{ cfg_addr_width-1 }}:0]       cfgIn_addr_del;
   logic [{{ cfg_bus_width-1 }}:0]        cfgIn_data_del;
   logic [{{ cfg_op_width-1 }}:0]         cfgIn_op_del;
   {% flop_inst = unique_inst('flop', 'cfgIn_floper', FLOP_WIDTH=cfg_addr_width+cfg_bus_width+cfg_op_width, FLOP_TYPE='rflop', FLOP_DEFAULT=0) %}
   {{ flop_inst.instantiate() }} (.Clk(Clk), .Reset(Reset),
			      .data_in({cfgIn.addr, cfgIn.data, cfgIn.op}),
			      .data_out({cfgIn_addr_del, cfgIn_data_del, cfgIn_op_del}));



   // internal wiring signals
   logic [{{ num_regs-1 }}:0]             onehot_en;
   logic                               addr_in_range;
   logic [{{ num_req_addr_bits-1 }}:0]    cfgIn_addr_del_int; // internal (shorter) address signal
   logic [{{ num_regs-1 }}:0]             regs_en;
   logic [{{ cfg_bus_width-1 }}:0]        regs_d[{{ num_regs-1 }}:0];
   logic [{{ cfg_bus_width-1 }}:0]        regs_q[{{ num_regs-1 }}:0];

   // make sure that the input address is in range
   assign addr_in_range =
              (({{ base_addr_hex }} == cfgIn_addr_del[{{ base_addr_range }}]) &&
               (cfgIn_addr_del[{{ usable_addr_range }}] < {{ num_req_addr_bits+1 }}'d{{ num_regs }}))?
              1'b1: 1'b0;

   // Pick the right bits of the address signal (if out of range default to zero)
   assign cfgIn_addr_del_int[{{ num_req_addr_bits-1 }}:0] =
          (addr_in_range)? cfgIn_addr_del[{{ usable_addr_range }}]: '0;

   // For config writes, there can be at most onehot enable signal
   always_comb begin
      onehot_en = '0;
      onehot_en[cfgIn_addr_del_int] = (cfgIn_op_del == {{ wrop }}) && (addr_in_range == 1'b1);
   end

   // assign the config output ports
   assign cfgOut.data =
                  // if not in range, pass the signal to the next guy
                  (addr_in_range != 1'b1) ? cfgIn_data_del :
                  // if in range and this is a readop... read
                  (cfgIn_op_del == {{ rdop }}) ? regs_q[cfgIn_addr_del_int] :
                  cfgIn_data_del;
   assign cfgOut.addr = cfgIn_addr_del;
   assign cfgOut.op =
                  // if not in range pass the signal to next guy
                  (addr_in_range != 1'b1) ? cfgIn_op_del :
                  // if in range (and not a nop) mark as done (bypass)
                  (cfgIn_op_del != {{ nop }}) ? {{ bypassop }}:
                  {{ nop }};    // else, it's just a nop.


   // Instantiate all the registers:
   // ==============================
   {% cnt = 0 %}
   {% for reg in reg_list: %}
   {%     params = {} %}
   {%     ## Match flop type to config/debug function: %}
   {%     ##   i->flop, ie->eflop, io->rflop, ieo->reflop, o->reflop %}
   {%     params['FLOP_TYPE'] = 'reflop' # default flop type %}
   {%     _ieo = reg['IEO'].lower() %}
   {%     if _ieo == 'i': %}
   {%         params['FLOP_TYPE'] = 'flop' %}
   {%     endif %}
   {%     if _ieo == 'ie': %}
   {%         params['FLOP_TYPE'] = 'eflop' %}
   {%     endif %}
   {%     if _ieo == 'io': %}
   {%         params['FLOP_TYPE'] = 'rflop' %}
   {%     endif %}
   {%     params['FLOP_WIDTH'] = reg['width'] %}
   {%     if 'default' in reg: %}
   {%         params['FLOP_DEFAULT'] = reg['default'] %}
   {%     endif %}
   {%     flop_inst = unique_inst('flop', reg['name'] + "_reg", **params) %}

   // register #{{ cnt }}:
   // name:{{ reg['name'] }}, type:{{ reg['IEO'] }}, width:{{ reg['width'] }}
   {%     ## Pick the right enable signal based on parameters %}
   {%     if 'e' in reg['IEO'].lower(): %}
   // flop on input_en or on cfg writes
   assign regs_en[{{ cnt }}] = {{ reg['name'] }}_en | onehot_en[{{ cnt }}];
   {%     elif 'i' in reg['IEO'].lower(): %}
   // flop input with no qualifier
   assign regs_en[{{ cnt }}] = 1;
   {%     else: %}
   // flop input only on cfg writes
   assign regs_en[{{ cnt }}] = onehot_en[{{ cnt }}];
   {%     endif %}
   {%  %}
   {%     ## Pick the right data input based on parameters %}
   {%     if 'i' not in reg['IEO'].lower(): %}
   // input only from cfg bus
   assign regs_d[{{ cnt }}][{{ reg['width']-1 }}:0] =
                                cfgIn_data_del[{{ reg['width']-1 }}:0];
   {%     else: %}
   // give priority to cfg bus writes, otherwise input from module input
   assign regs_d[{{ cnt }}][{{ reg['width']-1 }}:0] =
                     (onehot_en[{{ cnt }}])?cfgIn_data_del[{{ reg['width']-1 }}:0]:
                                         {{ reg['name'] }}_d[{{ reg['width']-1 }}:0];
   {%     endif %}
   {%  %}
   {{ flop_inst.instantiate() }}
     (.Clk(Clk),
      {%     if 'r' in params['FLOP_TYPE'].lower(): %}
      .Reset(Reset),
      {%     endif %}
      {%     if 'e' in params['FLOP_TYPE'].lower(): %}
      .Enable(regs_en[{{ cnt }}]),
      {%     endif %}
      .data_in(regs_d[{{ cnt }}][{{ reg['width']-1 }}:0]),
      .data_out(regs_q[{{ cnt }}][{{ reg['width']-1 }}:0]));

   {%     if 'o' in reg['IEO'].lower(): %}
   // assign value to the relevant output
   assign {{ reg['name'] }}_q[{{ reg['width']-1 }}:0] = regs_q[{{ cnt }}][{{ reg['width']-1 }}:0];
   {%     endif %}
   {%     if cfg_bus_width > reg['width']: %}
   // pad the config bus with zeros
   assign regs_q[{{ cnt }}][{{ cfg_bus_width-1 }}:{{ reg['width'] }}] = '0;
   {%     endif %}

   {%     cnt += 1 %}
   {% endfor %}
endmodule // {{ mname }}
