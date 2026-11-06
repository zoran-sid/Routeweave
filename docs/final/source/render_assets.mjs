import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dir = path.join(root, 'assets');
await fs.mkdir(dir, {recursive:true});
const esc = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;');
function svgDiagram(w,h,nodes,edges,extras=[]) {
  let s = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="100%" height="100%" fill="white"/><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="none" stroke="#526575"/></marker></defs>`;
  for (const [x1,y1,x2,y2,label] of edges) {
    s+=`<path d="M${x1},${y1} L${x2},${y2}" stroke="#526575" fill="none" stroke-width="2" marker-end="url(#arrow)"/>`;
    if(label)s+=`<text x="${(x1+x2)/2+7}" y="${(y1+y2)/2-8}" font-family="Heiti SC,Arial" font-size="18" fill="#526575">${esc(label)}</text>`;
  }
  for (const [x,y,width,height,title,body] of nodes) {
    s+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="#f4f7fa" stroke="#8093a3" stroke-width="1.4"/><text x="${x+width/2}" y="${y+34}" text-anchor="middle" font-family="Heiti SC,Arial" font-size="24" font-weight="bold" fill="#193247">${esc(title)}</text>`;
    for(const [i,line] of body.split('\n').entries())s+=`<text x="${x+width/2}" y="${y+65+i*26}" text-anchor="middle" font-family="Heiti SC,Arial" font-size="20" fill="#364a5a">${esc(line)}</text>`;
  }
  for (const [x,y,t] of extras)s+=`<text x="${x}" y="${y}" font-family="Heiti SC,Arial" font-size="19" fill="#526575">${esc(t)}</text>`;
  return s+'</svg>';
}
const architecture=svgDiagram(1200,510,[
 [30,30,245,115,'源数据与质量','YHT\n空间 空域 暴露 源清单'],
 [340,30,245,115,'风险编译','LQ\n任务窗 E×C 未知标记'],
 [650,30,245,115,'版本映射与发布','ZQO\n不可变快照 当前指针'],
 [650,230,245,115,'固定快照规划','ZC\nQ1航线 Q2航段状态'],
 [340,230,245,115,'结果验收','LJ\n当前推荐 历史查看'],
 [30,230,245,115,'消费与解释','调度与运营\n路线 指标 版本 来源'],
 [940,145,235,145,'审计与重放','成功事务与发件箱\n失败尝试记录\n源对象与历史快照'],
],[[275,85,340,85],[585,85,650,85],[770,145,770,230],[650,285,585,285],[340,285,275,285],[895,85,1057,85],[1057,85,1057,145]],[[30,410,'已验证范围：合成平地数据、固定任务窗口、本地 SQLite 事务目录'],[30,450,'部署设计：身份服务、外部通知投递、监控管道及跨机恢复']]);
const model=svgDiagram(1200,500,[
 [20,30,230,120,'Source','来源 许可 方法\n精度 有效时间'],
 [340,30,240,120,'Source snapshot','建筑 地形 空域\n暴露 覆盖 源版本'],
 [680,30,240,120,'Query snapshot','五类查询组件\nlineage与编译窗口'],
 [680,270,240,120,'Release','发布编号 父发布\n摘要 head 审计'],
 [340,270,240,120,'Query result','路径 航段 指标\n状态 窗口 版本'],
 [20,270,230,120,'Audit event','操作 角色 原因\n时间 关联标识'],
],[[250,90,340,90,'1:n'],[580,90,680,90,'派生'],[800,150,800,270,'发布'],[680,330,580,330,'1:n'],[340,330,250,330,'关联']],[[25,455,'源五版与查询五版分别保存，通过完整源对象、摘要和逐项映射连接']]);
for (const [name,svg] of [['architecture',architecture],['data-model',model]]) {
  await fs.writeFile(path.join(dir,name+'.svg'),svg);
  await sharp(Buffer.from(svg)).resize({width:1800}).png().toFile(path.join(dir,name+'.png'));
}
console.log('Rendered two technical diagrams');
