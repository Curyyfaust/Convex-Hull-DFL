import pandapower.networks as pn
import pandapower as pp
import numpy as np
import matplotlib.pyplot as plt

def DFLieee33(wind_power_list, sunny_power=None):  # 修改参数名以表示是列表
    pi_G = 10
    pi_T = 20
    pi_penalty = 20  # 惩罚系数
    
    net = pn.case33bw()  # IEEE33
    
    # 放大所有负荷
    net.load['p_mw'] *= 2
    net.load['q_mvar'] *= 2
    
    # 将线路阻抗除以2
    net.line['r_ohm_per_km'] /= 2
    net.line['x_ohm_per_km'] /= 2
    
    # 风电 - 设置为可控制的静态发电机
    wind_buses = [6, 15, 25]
    
    # 确保输入数据长度匹配
    if isinstance(wind_power_list, (int, float)):
        wind_power_list = [wind_power_list] * len(wind_buses)  # 如果是单个值，复制到所有风电站
    elif len(wind_power_list) != len(wind_buses):
        # 如果长度不匹配，用第一个值填充或截断
        if len(wind_power_list) < len(wind_buses):
            wind_power_list = wind_power_list + [wind_power_list[0]] * (len(wind_buses) - len(wind_power_list))
        else:
            wind_power_list = wind_power_list[:len(wind_buses)]
    
    for i, bus in enumerate(wind_buses):
        wind_power = wind_power_list[i]
        pp.create_sgen(net, bus=bus-1, p_mw=wind_power, q_mvar=0.0,
                      controllable=True, max_p_mw=wind_power, min_p_mw=0.0,
                      name=f"Wind_{bus}")
    
    # DG 发电机
    dg_buses = [7, 13, 17]
    dg_bus_indices = [bus - 1 for bus in dg_buses]
    for i in dg_bus_indices:
        pp.create_sgen(net, bus=i, p_mw=2.0, q_mvar=0.0, name=f"DG at Bus {i+1}",
                       controllable=True, min_p_mw=0.0, max_p_mw=2.0, min_q_mvar=-0.5, max_q_mvar=0.5)
    
    # 删除现有的成本函数
    if len(net.poly_cost) > 0:
        net.poly_cost.drop(net.poly_cost.index, inplace=True)
    
    # 为外部电网设置购电成本函数
    for idx in net.ext_grid.index:
        pp.create_poly_cost(net, element=idx, et="ext_grid", cp1_eur_per_mw=pi_T)
    
    # 为所有可控的分布式电源设置成本函数
    for idx in net.sgen[net.sgen['controllable'] == True].index:
        sgen_name = net.sgen.loc[idx, 'name']
        bus_num = int(str(sgen_name).split('_')[1]) if '_' in str(sgen_name) else 0
        
        if 'DG' in str(sgen_name):
            pp.create_poly_cost(net, element=idx, et="sgen", cp1_eur_per_mw=pi_G)
        elif 'Wind' in str(sgen_name):
            # 找到对应的预测功率
            wind_idx = wind_buses.index(bus_num) if bus_num in wind_buses else 0
            predicted_power = wind_power_list[wind_idx]
            # 风电成本函数：线性系数为负的惩罚，常数项为正的惩罚基础成本
            pp.create_poly_cost(net, element=idx, et="sgen", 
                               cp1_eur_per_mw=-pi_penalty, 
                               cp0_eur=pi_penalty * predicted_power)
    
    # 运行最优潮流
    try:
        pp.runopp(net)
        #print("最优潮流求解成功")
    except:
        print("最优潮流求解失败")
        return None, None
    
    # 计算实际风电出力
    wind_sgen_indices = [i for i, name in enumerate(net.sgen['name']) if 'Wind' in str(name)]
    actual_wind_total = net.res_sgen.iloc[wind_sgen_indices]['p_mw'].sum()
    
    total_cost = net.res_cost
    
    # 提取决策变量
    # 外部电网功率
    ext_grid_p = net.res_ext_grid['p_mw'].values
                                                                                                                          
    # 可控分布式电源功率
    sgen_p = net.res_sgen['p_mw'].values
    
    # 合成决策变量数组：[外部电网功率, 分布式电源功率]
    decision_vars = np.concatenate([ext_grid_p, sgen_p])

    total_load = net.res_load['p_mw'].sum()
    total_generation = net.res_ext_grid['p_mw'].sum() + net.res_sgen['p_mw'].sum()
    
    # print(f"总负荷: {total_load:.4f} MW")
    # print(f"总发电量: {total_generation:.4f} MW")
    # print(f"功率平衡差: {abs(total_generation - total_load):.6f} MW")
    
    return total_cost, decision_vars