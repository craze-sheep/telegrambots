# B2B-20260531-013040

- Created: 2026-05-31 01:30:40
- Mode: centralized bot-to-bot manager
- Work dir: /home/lzy/project/方向研究
- User task: 你是我的博士科研规划助手，你的工作目录是/home/lzy/project/方向研究，我想研究世界模型的大方向，选取20篇有关的有代表性的顶会论文，把能得到论文和代码拉去下来放入/home/lzy/project/方向研究，仔细研究拆解每一篇论文，每一篇论文回答下面的这些问题：
论文:
1.核心研究问题是什么?
2.研究路线分成哪几个模块?
3.每个模块需要哪些方法、数据或实验条件?
4.哪些结果支撑毕业论文成立?
5.新生最应该优先学习哪些个概念或方法?
6.这个方向最大的风险点是什么?
7.做相近方向，最适合从哪个小问题切入?

最后汇总这些论文做出一整个并排对比表，分析除了上面问题的汇总外，还要有方向的科研流程，正真难点，通用方法，通用数据格式等等

## Topology

User <-> Supervisor <-> Planner / Researcher / Developer / Tester

Workers only report to Supervisor. Worker-to-worker messages are ignored by service logic.
