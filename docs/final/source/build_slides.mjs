// Editable presentation composition. Call buildDeck(presentation) inside an
// Artifact Session, or pass a Presentation.create({slideSize:{width:1280,height:720}}).
export const FONT = 'Heiti SC';
const C={ink:'#173247',muted:'#526575',teal:'#147D86',pale:'#EDF3F6',line:'#D3DDE4'};
export const notes = [
 'ZQO：SkyRoute服务于城市无人机配送调度。距离短并不保证满足建筑、限高和地面暴露条件，因此我们把数据管理与三维航线查询放在同一条链路中。Q1给出可行路线，Q2解释航段状态及来源。对象是模拟城市片区，当前成果是可复现的数据管理原型。来源：docs/final/report.md 第1—2节；docs/project-brief.md。',
 'ZQO：五个模块已经实际连通。YHT提供封存源和质量门禁，LQ编译任务窗口风险，ZQO绑定来源并原子发布，ZC固定快照规划，LJ区分当前推荐与历史查看。源版本和查询版本分别留存。查询返回前核对当前发布，旧结果保留历史用途。来源：docs/final/evidence/five-module.json；docs/integration/zqo-evidence.md；AWS Transactional outbox pattern https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html 。',
 'YHT：源场景为600×600米平地片区，基线有25栋建筑、6个地面分区和3个空域体。坐标使用共同参考平面和米制单位，时间是UTC半开区间。每个对象保留来源与质量，查询五版还包括风险模型与规划配置。版本哈希用于内容身份，不等于发布者签名。来源：docs/modules/yht/design.md；docs/modules/yht/results/scene.json。',
 'YHT：索引先减少候选，再由几何内核检查完整航段。表格直接引用历史JSON，单位为微秒。实验是Windows 11、Python 3.12.14、SQLite 3.53.1单进程内存库，80条Q2、每方法5轮，装载时校验源摘要，查询计时不含重算源摘要。当前生产候选为PostGIS，尚无实库测试。来源：docs/modules/yht/results/benchmark.json；SQLite R*Tree https://www.sqlite.org/rtree.html 。',
 'LQ：风险采用可解释代理。E表示归一化暴露，C表示条件后果系数，二者为合成量。按完整航段地面投影和任务窗口取最大q，再按航程累积。阈值0.9与5米影响包络都是演示配置，λ只表达允许范围内的偏好。累计R可以大于1，没有事故概率含义。来源：docs/modules/lq/design.md；docs/modules/zc/design.md。',
 'LQ：质量门禁同时检查源E/C和派生q，独立入口不能依赖最外层调用方。原生风险模块保留未知及时间缺口，当前YHT导出则明确拒绝。作者自审属于已测试的角色策略，真实API和数据库权限仍属部署设计。真实暴露数据应控制用途和粒度，并评估飞行负担在区域之间的转移。来源：docs/final/evidence/risk-review.json；docs/modules/lq/governance.md；PostgreSQL RLS https://www.postgresql.org/docs/18/ddl-rowsecurity.html 。',
 'ZC：搜索空间是有限26邻居三维网格，检查的是完整航段及其安全包络。风险和边长非负，欧氏长度下界使A*启发式一致。一次查询固定发布和任务窗，更新后复核旧路线并重新A*。Dijkstra作为对照，D* Lite作为尚未实施的增量候选。来源：docs/modules/zc/design.md；Dijkstra 1959 doi:10.1007/BF01386390；Hart等1968 doi:10.1109/TSSC.1968.300136；Koenig和Likhachev 2002 https://idm-lab.org/bib/abstracts/papers/aaai02b.pdf 。',
 'ZC：左图是历史10米网格实验的扩展节点数。空场和建筑场景A*扩展较少，禁飞墙必须穷尽可达子图，两者相同。右表是同一热点场景A*的风险偏好取舍，λ从0到2时航程增加14.2%，代理下降86.7%，不代表事故率变化。不同λ的目标J定义不同，跨权重比较用航程和R。来源：docs/modules/zc/results/benchmark.json；docs/modules/lq/results/evaluation.json。',
 'LJ：整链路采用20米网格、5米障碍缓冲、λ=0。发布2的新限制使旧路线5个航段禁止，新的空间路径不同但长度相同，风险代理增加。这说明等长绕行不能写成距离增加。撤销后发布3恢复原路线，源版本仍保留撤销历史。旧发布只能按显式历史查看验收。来源：docs/final/evidence/five-module.json，normal、updated_route、revoked_route、same_versions_stale_rejected。',
 'LJ：本轮在2850d89上重新运行模块回归、原审查、整链路和风险专项，四组均通过，分别报告而不混作单测总量。原型已证明版本、质量及失败处理机制可以组合。下一阶段针对真实几何、机型风险校准、并发、外部通知和恢复开展验证，性能目标需要部署环境支持。来源：docs/final/evidence/verification.json；课程要求见docs/course-requirements.md。',
];

export function buildDeck(p) {
  if(p.slides.items.length)p.slides.keep([]);
  function text(s,str,x,y,w,h,size=28,bold=false,color=C.ink,align='left'){
    const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
    a.text=str;a.text.style={typeface:FONT,fontSize:size,bold,color,alignment:align,verticalAlignment:'top',insets:0,autoFit:'none'};return a;
  }
  function slide(title,owner){
    const s=p.slides.add({width:1280,height:720});s.background.fill='#FFFFFF';
    text(s,title,64,44,1152,68,44,true);
    const n=p.slides.items.length;
    text(s,`SkyRoute   ${owner}`,64,670,950,24,18,false,C.muted);
    text(s,String(n),1156,670,60,24,18,false,C.muted,'right');
    s.speakerNotes.text=notes[n-1];return s;
  }
  function table(s,values,x,y,width,height,widths,size=25){
    const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width,height,columnWidths:widths,values});
    t.borders.assign({fill:C.line,width:1,style:'solid'});
    for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
      const a=t.getCell(r,c);a.fill=r===0?C.ink:(r%2===0?C.pale:'#FFFFFF');
      a.text.style={typeface:FONT,fontSize:size,color:r===0?'#FFFFFF':C.ink,bold:r===0,verticalAlignment:'middle'};
    }
    t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{top:10,bottom:10,left:14,right:14},anchor:'center'});
    return t;
  }
  // 1 — project and user value, also serving as the first speaker's opening.
  let s=slide('SkyRoute','ZQO');
  text(s,'城市三维无人机物流\n航线规划与数据管理',64,142,1100,155,56,true);
  text(s,'一次查询使用完整、适时、可追溯的输入',64,342,1110,64,36,false,C.teal);
  text(s,'Q1  查询可行航线\nQ2  解释航段约束、风险与数据来源',64,447,1050,100,30);
  text(s,'服务对象：调度员、运营人员、空域与安全管理员、系统管理员',64,595,1140,45,24,false,C.muted);
  // 2 — native editable architecture.
  s=slide('五模块架构与版本发布','ZQO');
  const labels=[['YHT','源数据与质量'],['LQ','任务窗风险编译'],['ZQO','来源映射与发布'],['ZC','固定快照规划'],['LJ','当前与历史验收']];
  labels.forEach(([a,b],i)=>{
    const x=64+i*232;
    const box=s.shapes.add({geometry:'rect',position:{left:x,top:178,width:205,height:130},fill:C.pale,line:{fill:'#8FA5B5',width:1}});
    box.text=`${a}\n${b}`;box.text.style={typeface:FONT,fontSize:26,bold:true,color:C.ink,alignment:'center',verticalAlignment:'middle',insets:10};
    if(i<4)s.shapes.add({geometry:'rightArrow',position:{left:x+209,top:231,width:20,height:20},fill:C.teal,line:{fill:'none',width:0}});
  });
  text(s,'源五版',64,365,180,40,28,true);
  text(s,'场景 / 地形 / 空域 / 暴露 / 来源',250,365,950,45,28);
  text(s,'查询五版',64,428,180,40,28,true);
  text(s,'场景 / 空域 / 风险数据 / 风险模型 / 规划配置',250,428,950,50,28);
  text(s,'不可变快照与原子指针保证读取组合\n返回前检查发布身份，来源映射支持历史重放',64,534,1140,94,30,false,C.teal);
  // 3 — data model.
  s=slide('城市数据模型与来源','YHT');
  table(s,[['数据','合成基线','关键内容'],['建筑与地形','25栋建筑，31×31地形点','轮廓、高程、坐标基准'],['空域限制','3个禁飞或限高体','几何、有效期、发布状态'],['地面暴露','6个区域','E / C / q、时间、来源'],['质量与清单','36个覆盖瓦片，5类来源','完整性、源版本、摘要']],64,145,1152,395,[235,430,487]);
  text(s,'600×600米源片区，局部米制坐标，UTC半开时间区间',64,570,1140,42,27,false,C.teal);
  // 4 — native evidence table.
  s=slide('空间索引减少候选几何检查','YHT');
  text(s,'三维包围盒取候选，再检查完整航段和安全包络',64,133,1140,52,30);
  table(s,[['建筑数','全扫 Q2 中位 μs','三维索引 Q2 中位 μs'],['200','984.90','76.65'],['800','3680.35','76.85'],['2400','10389.85','79.35']],64,220,1152,292,[210,460,482],26);
  text(s,'2,400栋时，平均候选由2,400个降至13.9个',64,548,1140,44,30,true,C.teal);
  text(s,'历史单机内存库实验，80条Q2、5轮；不含重复源摘要计算',64,610,1140,30,21,false,C.muted);
  // 5 — formulas and decision states.
  s=slide('后果加权暴露与风险硬约束','LQ');
  text(s,'q = E × C',64,155,575,75,48,true,C.teal);
  text(s,'r = (航段长度 / 100米) × q_max\nR = 所有航段 r 的累计',64,263,590,115,31);
  text(s,'E、C是归一化合成量\n按地面包络与任务窗取最大q\n累计R可大于1，不是事故概率',64,430,590,150,28);
  table(s,[['条件','处理'],['q ≥ 0.9','禁止航段'],['资料未知或时段缺口','未知或拒绝导出'],['已知且满足硬约束','比较距离与风险偏好']],700,169,516,365,[310,206],25);
  text(s,'0.9阈值及5米影响包络为演示配置',700,565,516,65,22,false,C.muted);
  // 6 — governance evidence.
  s=slide('质量门禁与安全治理','LQ');
  table(s,[['情境','处理原则','证据范围'],['源E/C缺失或q不一致','拒绝导出，保留原因','独立入口已验证'],['风险时段覆盖有缺口','保留未知空间与来源','风险模块已验证'],['草稿作者自行审批','职责分离，拒绝自审','角色策略模拟'],['敏感导出与跨组织访问','最小权限、用途和审计','部署验收设计']],64,150,1152,380,[330,495,327],25);
  text(s,'对外提供必要的状态与来源解释，限制细粒度暴露数据导出',64,568,1140,70,28,false,C.teal);
  // 7 — algorithm rationale.
  s=slide('固定版本上的三维航线搜索','ZC');
  text(s,'01  固定五类输入和任务窗口\n02  检查完整三维航段与包络\n03  在已知允许图上运行A*\n04  复核路径并返回版本来源',64,155,670,300,32);
  text(s,'26邻居三维网格',790,165,420,50,32,true,C.teal);
  text(s,'h = 到目标的欧氏距离 / 100米',790,255,420,100,28);
  text(s,'边代价非负\n启发式不高估剩余代价',790,395,420,100,28);
  text(s,'Dijkstra提供对照；更新后全量A*，D* Lite保留为后续候选',64,560,1140,74,28,false,C.muted);
  // 8 — actual native chart and tradeoff table.
  s=slide('搜索效率与风险权重取舍','ZC');
  text(s,'扩展节点数',64,135,670,42,27,true);
  const chart=s.charts.add('bar',{
    position:{left:64,top:190,width:640,height:375},
    categories:['空场','建筑','禁飞墙'],
    series:[{name:'Dijkstra',values:[661,699,364],fill:C.ink},{name:'A*',values:[11,72,364],fill:C.teal}],
    barOptions:{direction:'column',grouping:'clustered',gapWidth:80},
    hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:22}},
    xAxis:{textStyle:{fontSize:22}},yAxis:{min:0,max:800,majorUnit:200,textStyle:{fontSize:19},majorGridlines:{fill:C.line,width:1}},
    dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:20}},
  });
  text(s,'同一热点场景的A*',762,135,454,42,27,true);
  table(s,[['λ','航程 m','代理R'],['0','116.57','0.5021'],['2','133.14','0.0666'],['8','133.14','0.0666']],762,207,454,276,[70,192,192],24);
  text(s,'航程增加14.2%\n累计代理下降86.7%',762,524,454,90,28,true,C.teal);
  text(s,'历史10米网格合成实验；相同λ内比较目标代价，代理变化不等于事故率变化',64,625,1150,30,20,false,C.muted);
  // 9 — observed integration behavior.
  s=slide('更新后的推荐与历史结果','LJ');
  table(s,[['发布阶段','航程 m','代理R','实际表现'],['1 正常','612.5483','4.212039','完整链路验收通过'],['2 新禁飞','612.5483','4.452608','旧路线5段禁止，改走等长路径'],['3 撤销','612.5483','4.212039','恢复路线，保留撤销来源']],64,157,1152,300,[210,220,220,502],24);
  text(s,'旧发布标记stale，当前推荐验收失败\n明确选择历史查看时可重放，组件同版也需核对发布身份',64,511,1140,110,29,false,C.teal);
  // 10 — verification and scope.
  s=slide('验证结果与下一阶段','LJ');
  table(s,[['检查组','通过数量','关注点'],['五模块回归','131 / 131','几何、风险、发布与验收'],['原问题审查','7 / 7','输入质量、缓冲与版本'],['五模块整链路','11 / 11','更新、撤销、审计及重开'],['风险专项','25 / 25','独立入口、时间窗与来源']],64,150,1152,350,[360,225,567],25);
  text(s,'已验证：合成平地、固定任务窗、本地SQLite原型',64,535,1140,45,29,true,C.teal);
  text(s,'下一阶段：真实几何与风险校准、并发访问、外部通知及恢复',64,602,1140,38,25,false,C.muted);
  return {slides:p.slides.items.length,chart};
}
