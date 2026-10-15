# Software-engineering analogues for fault difficulty (detect / localize / repair), as covariates for single-fault RTL mutant benchmarks

Scope note: research done 2026-10-15, about 18 search/fetch calls. Verification level is marked per claim. "[abstract/summary only]" means I saw only the abstract, a search snippet, or a secondary summary, not the full paper. Two primary pages returned HTTP 403 and could not be read directly: the OpenAI SWE-bench Verified blog and the Yao et al. ICSE'14 PDF.

## 1. Mutant hardness / stubbornness / subsumption: which operators and properties make mutants hard?

### Takeaway
Mutant hardness is very unevenly spread across operators. Logical-connector replacement (LCR) makes many stubborn (hard to kill but not equivalent) mutants. ABS and part of UOI mostly make equivalent mutants. Raw mutation scores are inflated by redundant (subsumed) mutants and confounded by test-suite size. Cheap structural features grouped by PIE (execution, infection, propagation) predict kill or survive with AUC above 0.8, but much of that comes from the trivial "not covered" case.

### Cited Findings
- Yao, Harman & Jia, "A Study of Equivalent and Stubborn Mutation Operators using Human Analysis of Equivalence" (ICSE 2014, pp. 919–930). They hand-analysed 1,230 mutants from 18 programs and found a highly uneven spread of equivalence and stubbornness across operators. ABS and half of UOI made many equivalent mutants and almost no stubborn ones. LCR made many stubborn mutants and few equivalent ones. A stubborn mutant is non-equivalent but survives a high-quality test suite. Implications drawn by the authors: (a) earlier fault-seeding test-effectiveness studies may be skewed; (b) tools should favour operators that produce many stubborn and few equivalent mutants. [abstract/summary only; PDF returned 403, so I could not extract per-operator percentages] — [UCL Discovery](https://discovery.ucl.ac.uk/id/eprint/1508140/), [PDF](https://discovery-pp.ucl.ac.uk/id/eprint/1508140/1/icse14-xy.pdf)
- Follow-up work on killing stubborn mutants with symbolic execution exists (arXiv 2001.02941). I did not read it. — [arXiv](https://arxiv.org/pdf/2001.02941)
- Just et al., "Are Mutants a Valid Substitute for Real Faults in Software Testing?" (FSE 2014; ACM SIGSOFT Distinguished Paper; FSE Most Influential Paper award 2024). They studied 357 real faults in 5 open-source applications (321 KLOC). 73% of real faults were coupled to mutants from common operators. On average about 2 mutants were coupled to each real fault. The other 27% were not coupled, because operators were weak (e.g., argument swap) or missing (type conversion), or because no operator could model the fault (algorithm change, code deletion). Mutant detection correlated significantly with real-fault detection after controlling for coverage. [abstract + slides summary; correlation coefficients not extracted] — [Paper PDF](https://people.cs.umass.edu/%7Erjust/publ/mutants_real_faults_fse_2014.pdf), [Abstract page](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html), [Award news](https://news.cs.washington.edu/2024/08/21/marvelous-mutants-allen-schools-rene-just-and-michael-ernst-receive-fse-most-influential-paper-award-for-showing-the-validity-of-mutants-in-software-testing)
- Papadakis, Shin, Yoo & Bae, "Are Mutation Scores Correlated with Real Fault Detection? A Large Scale Empirical Study…" (ICSE 2018). Using CoreBench and Defects4J, they found that the reported correlations come mainly from the confounding effect of test-suite size. Once size is controlled, all correlations between mutation score and real-fault detection are weak. Even so, suites ranked top by mutation score detected faults better than random suites of the same size. [abstract/summary only] — [ICSE 2018 page](https://conf.researchr.org/details/icse-2018/icse-2018-Technical-Papers/78/Are-Mutation-Scores-Correlated-with-Real-Fault-Detection-A-Large-Scale-Empirical-stu), [IEEE](https://ieeexplore.ieee.org/document/8453121)
- Papadakis et al. (ISSTA 2016) argue that including subsumed (redundant) mutants can artificially inflate how well a test technique appears to detect faults. They recommend scoring only subsuming mutants. [summary only; I did not confirm the title or author list from the page itself] — [UCL PDF](https://discovery-pp.ucl.ac.uk/id/eprint/1508136/1/ISSTA16.pdf)
- Predictive Mutation Testing (Zhang et al., ISSTA 2016; TSE 2018 extension). A classifier on PIE-grouped features predicts mutant kill without running the mutant, tested on 163 projects. Example features: execution (number of covering tests), infection (operator type), propagation (e.g., inheritance depth). It reached AUC above 0.80 on most projects with up to 151.4x speedup. Feature count of about 14 comes from a secondary source and is unverified. [secondary summaries] — [FB Research page](https://research.fb.com/publications/predictive-mutation-testing/), [UCL TSE version](https://discovery.ucl.ac.uk/id/eprint/10051793/)
- Caveat: a 2020 study found that PMT results are inflated by uncovered mutants, which trivially survive. AUC drops significantly once unreached mutants are removed. Mao et al. later used 95 features and 11 classifiers. — [arXiv 2005.11532](https://arxiv.org/pdf/2005.11532), [Contextual PMT](https://ar5iv.labs.arxiv.org/html/2309.02389)
- LLM-generated mutants on 851 real Java bugs were behaviourally closer to real faults. They detected about 93% of real bugs, against 74% for traditional tools, but had more non-compiling and equivalent mutants. [summary only] — [arXiv 2406.09843](https://arxiv.org/html/2406.09843v2)

### Inferences
- For RTL mutants, **operator class** should be a first-class covariate. The software evidence says hardness clusters by operator. Logical-connector and condition mutations (LCR, ROR-like) are the likeliest stubborn sources. Absolute-value-like and unary-insertion mutations are the likeliest equivalent sources. Expect RTL analogues to follow: `&&`/`||` and `&`/`|` swaps, and comparison-operator changes in enable or guard logic.
- **Reachability (execution) features alone predict a lot of "hardness" trivially**, as the PMT critique shows. A difficulty covariate set should therefore separate "not reached by the stimulus" from "reached but masked". In RTL, use (a) toggle or line coverage of the mutated statement under the provided testbench and (b) whether the infected signal reaches a checked output.
- Because subsumed mutants inflate apparent detectability, a benchmark should dedupe mutants by kill-set, or at least report how many mutants share the same failing-test signature.
- About 27% of real faults have no coupled simple mutant (Just et al.). A single-operator RTL mutant benchmark therefore systematically under-represents algorithmic, deletion-style and missing-logic bugs.

### Gaps
- Per-operator stubbornness and equivalence percentages from Yao et al. were not extracted (PDF 403).
- I found no software study that directly gives "hard-to-kill" rates by mutation depth or propagation distance with numbers. Laurent et al.'s higher-order-mutant coupling work on Defects4J 2.0 was not retrieved.
- The Just et al. correlation coefficients were not extracted.

## 2. Fault observability and propagation (PIE / RIPR, failed error propagation, coincidental correctness)

### Takeaway
PIE / RIPR splits detection into reach, infect, propagate and (for RIPR) reveal by an oracle. Empirically, failed error propagation (FEP) is negligible for real Java faults at unit level. It is substantial at system level (about 11% of executions) and higher for mutants than for real faults. Coincidental correctness (CC) is common and measurably degrades coverage-based fault localization.

### Cited Findings
- PIE (Voas): testability is estimated as three probabilities: the location is executed, execution infects the data state, and the infected state propagates to output. This underlies "sensitivity analysis". Infection analysis is the most expensive step. Tool: PISCES. [secondary sources; the 1992 IEEE TSE 18(8) citation is from memory and was not verified] — [NASA NTRS](https://ntrs.nasa.gov/api/citations/20040121153/downloads/20040121153.pdf), [Mutant-schemata automation](https://ccis2k.org/iajit/index.php/archive/volume-9-2012/may-2012-no-3/item/2137-partial-automation-of-sensitivity), [PISCES](https://www.academia.edu/894222/PISCES_A_tool_for_predicting_software_testability)
- Jahangirova, Clark, Harman & Tonella, "An Empirical Study on Failed Error Propagation in Java Programs with Real Faults" (arXiv 2011.10787, 2020; no venue listed). Results:
  - **Unit level:** 386 Defects4J bugs, 459 changed methods, 258,372 executions. 53.8% exposed the fault externally and **0 showed FEP** (95% upper bound about 1e-5).
  - **System level:** Closure, 22 executed bugs, 528 executions. 80.3% were externally detectable and **11.4% showed FEP** (95% CI about 8.8–14.4%), spread across 4 bugs.
  - **Mutants:** 1.6% internal and 3.7% external FEP, against zero for real faults at unit level.
  - **Why FEP was absent:** in about 35% of methods (161/459) the fix changes a return or adds an if-block with return or throw, so FEP is impossible. In about 13% the state change always reaches the return value.
  - **Authors' warning:** mutants may mislead oracle-placement decisions because they propagate differently from real faults.

  — [arXiv HTML](https://arxiv.org/html/2011.10787)
- Masri & Assi (ACM TOSEM 23(1), 2014). Coincidental correctness is prevalent in both weak form (reached) and strong form (reached and infected), and it reduces the safety of coverage-based fault localization. Their best test-suite cleansing method improved FL safety for 88% of programs and precision for 61%. [summary only] — [ResearchGate](https://www.researchgate.net/publication/262164188_Prevalence_of_Coincidental_Correctness_and_Mitigation_of_its_Impact_on_Fault_Localization)
- Abou Assi et al., "Coincidental correctness in the Defects4J benchmark" (STVR 2019). CC appears at all testing levels and is more prevalent at higher (system) levels than at lower (unit) levels. [abstract only; percentages not extracted] — [arXiv 1808.09233](https://arxiv.org/pdf/1808.09233), [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1002/stvr.1696)
- Androutsopoulos et al. (ICSE 2014) related conditional entropy (information loss, or "squeezing") to FEP. I could not locate or verify its text or numbers. — (no verified link)

### Inferences
- The unit-level vs system-level contrast (0% vs 11.4% FEP) maps directly onto RTL. A fault deep inside a datapath, observed only at top-level ports after many cycles, is the "system-level" case. **Propagation distance and depth** should be strong difficulty covariates. Candidate cheap measures:
  - **Structural:** number of register stages or combinational levels from the mutated signal to the nearest checked output, and fan-out cone size.
  - **Temporal:** counterexample or first-divergence cycle in simulation or BMC.
  - **Masking proxy:** fraction of stimulus cycles where the mutated node differs (infection) but outputs match (CC). Compute it by co-simulating golden and mutant with an internal-signal diff.
- RTL designs have extensive information-losing structures (muxes, enables, reductions, truncation), which plausibly favour FEP and CC more than small Java methods. The authors themselves credit small Java methods for low "information squeezing". This is an inference, not a measured result.
- Because mutants showed more FEP than real faults, propagation-based difficulty may be **over-represented** in a mutant benchmark relative to real RTL bugs.

### Gaps
- No quantitative measure of how much CC degrades SBFL rank (e.g., EXAM score deltas) was extracted.
- No RIPR-specific empirical numbers (Li & Offutt's revealability extension) were retrieved.
- The Androutsopoulos et al. numbers were not verified.

## 3. Fault localization difficulty predictors

### Takeaway
The strongest documented warning is that FL results on artificial faults do not predict results on real faults (Pearson et al., ICSE 2017). Mutation-based FL looked better only on artificial faults. For LLM-based FL there is anecdotal and secondary evidence that multiple failing tests and issue texts without location clues make localization harder. I found no clean quantitative breakdown by number of failing tests or hunk count.

### Cited Findings
- Pearson et al., "Evaluating and Improving Fault Localization" (ICSE 2017, pp. 609–620).
  - **Artificial faults:** they replicated 10 published claims on 2,995 artificial faults in 6 programs. 7 claims were supported statistically, but only 3 had non-negligible effect sizes.
  - **Real faults:** on 310 real faults from the same programs, results disagreed with prior studies. The slides say artificial-fault FL performance "is not predictive" of real-fault performance, mutation-based FL was better only on artificial faults, and SBFL formulas were roughly equivalent.

  — [Paper PDF](https://homes.cs.washington.edu/~rjust/publ/fault_localization_effectiveness_icse_2017.pdf), [Slides](https://people.cs.umass.edu/~rjust/publ/fault_localization_effectiveness_icse_slides_2017.pdf), [Abstract](https://homes.cs.washington.edu/~mernst/pubs/fault-localization-icse2017-abstract.html)
- Zou, Liang, Xiong, Ernst & Zhang, "An Empirical Study of Fault Localization Families and Their Combinations" (TSE 2019). Combining FL techniques gives a reported 200% increase in faults localized at Top-1 over any single technique. Per-fault-type breakdowns were not extracted. [abstract only] — [arXiv 1803.09939](https://arxiv.org/abs/1803.09939)
- LLM FL and failing tests:
  - A secondary summary of an LLM FL system ("SemiAutoFL") says it localized accurately with one failing test but struggled when a bug caused several. Unverified and no numbers.
  - The AgentFL authors note that one fault often triggers many failing tests (e.g., Chart-26 has 22), so their design focuses on one failing test class.

  [secondary/snippet] — [AgentFL (OpenReview)](https://openreview.net/attachment?id=kdQ50AXRPT&name=pdf), [AutoFL (Kang et al.)](https://arxiv.org/html/2308.05487v3), [LLM FL empirical study](https://arxiv.org/pdf/2510.20521)
- If fault-triggering tests are edited after the bug report (data "uncleanness"), SBFL is significantly worse on all metrics, so the quality of failing tests matters. [summary only] — [arXiv 2310.19139](https://arxiv.org/pdf/2310.19139)
- An anatomy of 488 Defects4J faults based on control-flow and data-flow graph representations exists. It is relevant for structural fault features, but I did not read it. — [arXiv 2502.02299](https://arxiv.org/pdf/2502.02299)
- On SWE-bench, the hardest problems are those whose issue description gives no clue to the location. Problem rates in SWE-bench Lite: 4.3% had the exact patch in the description, 10.0% lacked critical information, and 5.0% had misleading solutions. These led to SWE-bench Lite-S. This is attributed to the Agentless paper (Xia et al., 2024) based on a search summary. I did not fetch the paper. [snippet only]
- SWE-bench leaderboard analysis: file-level localization is relatively strong, line-level localization has much more room to improve. [summary only] — [arXiv 2506.17208](https://arxiv.org/html/2506.17208v1)

### Inferences
- The Pearson et al. result is the most directly transferable caution. A mutant-only RTL benchmark may rank localization methods differently from how they would rank on real RTL bugs, especially spectrum-based or mutation-based localizers.
- Cheap RTL localization-difficulty covariates suggested by the software evidence:
  - **Number and diversity of failing tests or assertions.** Direction is uncertain: more failures give more signal for SBFL but can confuse LLM FL.
  - **Whether the failure message or waveform names a signal in the mutated module.** This is the "location clue" analogue.
  - **Hierarchy distance** from the first failing check to the mutated module.
  - **Size of the suspicious set,** for example the cone-of-influence size from failing outputs.

### Gaps
- I found no study that quantifies LLM FL accuracy against number of failing tests or against single-line vs multi-hunk faults with numbers.
- Zou et al.'s per-fault-class results were not extracted.

## 4. APR and LLM-agent repair difficulty (SWE-bench Verified and predictors of agent success)

### Takeaway
On SWE-bench Verified, human time-to-fix buckets track gold-patch size: about 5, 14 and 56 LOC for easy, medium and hard; hunks 1.4 → 2.5 → 6.8; files 1.0 → 1.3 → 2.0. Agent success falls steeply with bucket. For example, the union of top systems solves about 95% of easy tasks but only about 42% of hard ones. A 2026 study of 45.8K tasks finds difficulty is largely predictable from static patch and repo features (AUC 0.863). Patch fragmentation (lines deleted, number of hunks, gap between hunks) and repo scale dominate. Issue-text features matter mainly for mid-difficulty tasks.

### Cited Findings
- **SWE-bench Verified construction (OpenAI, 2024).** 500 tasks. Three annotators per sample rated issue clarity, test validity, and estimated time-to-fix for an engineer familiar with the codebase. OpenAI included as many 1–4 h and >4 h samples as possible and sampled the rest at random. [OpenAI page returned 403; details via secondary sources] — [OpenAI blog](https://openai.com/index/introducing-swe-bench-verified/), [Epoch AI](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate)
- **Bucket sizes.** <15 min: 194 (38.8%). 15–60 min: 261 (52.2%). 1–4 h: 42 (8.4%). >4 h: 3 (0.6%). — [Ganhotra blog, Apr 2025](https://jatinganhotra.dev/blog/swe-agents/2025/04/15/swe-bench-verified-easy-medium-hard.html). Epoch gives 39% / 52% / about 8% / 3 tasks. — [Epoch AI](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate). Note: some secondary sources say 196 in the easiest bucket; the 194 count is the one I verified.
- **Gold-patch size by bucket** (Ganhotra).

  | Bucket | Files | Hunks | Lines |
  |---|---|---|---|
  | Easy | 1.03 | 1.37 | 5.04 |
  | Medium | 1.28 | 2.48 | 14.1 |
  | Hard (≥1 h) | 2.0 | 6.82 | 55.78 |

  Multi-file tasks are 14.2% of Verified overall: 3.1% of easy, 15.3% of medium and 55.6% of hard. For comparison, 24.9% of the SWE-bench test set and 50.3% of the train set are multi-file. Epoch independently reports about 5, 14 and 50 LOC per bucket and says time estimates correlate with gold-patch lines changed. — [Ganhotra](https://jatinganhotra.dev/blog/swe-agents/2025/04/15/swe-bench-verified-easy-medium-hard.html), [Epoch](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate)
- **Resolve rate by bucket** (Ganhotra, leaderboard snapshot of early 2025).

  | System | Easy | Medium | Hard |
  |---|---|---|---|
  | Union of systems | 95.4% | 84.3% | 42.2% |
  | Augment Agent v0 | 80.4% | 62.1% | 20.0% |
  | AgentScope | 81.4% | 56.7% | 24.4% |
  | Agentless-1.5 + Claude 3.5 Sonnet | 70.6% | 42.5% | 13.3% |
  | SWE-agent + GPT-4o | 36.6% | 16.9% | 2.2% |
  | SWE-agent + Claude 3 Opus | 27.3% | 10.0% | 0% |

  In the hard bucket, the union solved 10 of 20 single-file tasks but only 9 of 25 multi-file tasks. — [Ganhotra](https://jatinganhotra.dev/blog/swe-agents/2025/04/15/swe-bench-verified-easy-medium-hard.html)
- **Newer models (Vals.ai, 2026).** Per-bucket rates are shown for 88 models. The search summary reports top 2026 entries at about 90–98% in the 1–4 h bucket. Mid-tier entries fall from about 90% to 79% to 64% (e.g., an entry labelled Claude Opus 4.7). [UNVERIFIED: search-summary only; model names and numbers not checked on the page] — [Vals.ai](https://www.vals.ai/benchmarks/swebench)
- **Bucket validity.** METR found the time estimates optimistic: two 1–4 h tasks took baseliners 2–3 h. Epoch found 85 tasks (17%) unsolved by the top 5 submissions and judged 14 of 40 reviewed hard tasks invalid, so roughly a 5–10% invalid-sample rate overall. Django accounts for about half of tasks, and the top 5 repos for over 80%. Contamination risk is rated high. — [Epoch](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate), [METR long-tasks paper](https://arxiv.org/pdf/2503.14499)
- **Scaffold effect.** The same model can gain up to about 20 points from its scaffold: GPT-4o goes from 23% with SWE-agent to 33.2% with Agentless, and Claude 3.7 from 62.3% to 70.2% with a custom scaffold. — [Epoch](https://epoch.ai/blog/what-skills-does-swe-bench-verified-evaluate)
- **Al-Haque & Johnson, "What Makes Software Issue Resolution Tasks Difficult for Agents?"** (arXiv 2608.18280, Aug 2026; accepted ESEM 2026).
  - **Data:** 45,769 tasks (SWE-Smith and SWE-Rebench; 1,553 repos), about 220K trajectories, Qwen3-Coder-480B in OpenHands.
  - **Prediction with XGBoost on 54 static features:** any-success AUC 0.863. Patch-only AUC 0.846, repo-only 0.839, prompt-only 0.599. Adding prompt features to patch and repo features adds at most 0.002 AUC.
  - **Top SHAP features:** lines deleted (0.406), number of hunks, and mean gap between hunks, together 29% of total importance. Next is the repo's count of top-level directories. Higher values of each mean failure.
  - **Prompt features** are in the top 5 for 70.3% of mid-difficulty tasks, but only 26.8% of easy and 6.8% of hard tasks.
  - **Caveat:** files-changed and total-lines were dropped for collinearity, so they are not reported separately.

  — [arXiv HTML](https://arxiv.org/html/2608.18280)
- **Liu et al., "Rethinking APR: The Impact of Bug Complexity, Fault Localization, and LLM Cost-efficiency"** (arXiv 2608.14065, Aug 2026; accepted ESEM 2026). Structurally complex bugs are harder, but more than 50% of moderately complex bugs can be repaired by low-cost LLM APR. Imprecise localization makes repair harder and widens the gap between ChatRepair and CodeCorrector. Higher-cost or higher-reasoning settings do not consistently improve cost-efficiency. [abstract only; no numeric effect sizes] — [arXiv](https://arxiv.org/abs/2608.14065)
- **Bug reports for repair agents** (arXiv 2607.09553). Difficulty and gold-patch size are consistently and negatively associated with success for all three LLMs. Better reports help but cannot fully make up for fix complexity. [snippet only] — [arXiv](https://arxiv.org/pdf/2607.09553)
- **SWE-bench Pro** is about 80% multi-file vs about 14% for Verified, as cited by a multi-file localization study. That study also reports that naive file-system access can hurt localization. [secondary] — [arXiv 2606.11976](https://arxiv.org/html/2606.11976v1)
- **Behaviour of agents vs developers.** Agents prefer localized, minimal edits, while developers restructure more. [summary only] — [arXiv 2506.08311](https://arxiv.org/pdf/2506.08311)
- **Failure taxonomy studies** exist for issue-solving agents (arXiv 2509.13941) and for agent bug fixing (Meng et al., arXiv 2411.10213). I did not read their numbers. — [arXiv 2509.13941](https://arxiv.org/pdf/2509.13941), [arXiv 2411.10213](https://arxiv.org/html/2411.10213v1)

### Inferences
- **Does the agentic advantage grow with difficulty?** From Ganhotra's table, compare the best agentic systems (Augment, AgentScope) with Agentless-1.5 + Claude 3.5 Sonnet:
  - The relative advantage is about 1.14x on easy (80.4 vs 70.6), about 1.46x on medium (62.1 vs 42.5), and about 1.5–1.8x on hard (20–24.4 vs 13.3).
  - The absolute gap is about 10 points on easy and medium, and 7–11 points on hard.
  - So the *relative* gain grows with difficulty. However, models and scaffolds differ between these entries, so this is confounded and only suggestive. I found no controlled same-model study of iterative vs single-shot by difficulty bucket.
- RTL translation of the strongest predictors:
  - **Patch fragmentation:** number of hunks or edit sites, gap between them, number of modules or files touched.
  - **Edit size:** lines added or deleted.
  - **Design scale:** number of modules, hierarchy depth, total LOC.

  For single-site mutants, patch size and fragmentation are nearly constant (1 hunk, 1–2 lines). That removes the dominant SWE-bench difficulty axes. Difficulty must then come from the localization and propagation axes (Q2, Q3) and from design size.
- Human time-to-fix labels are noisy (METR) and partly invalid (Epoch). Automatically computed covariates (cycle depth, cone size, failing-check count) may therefore be more reliable stratifiers than annotated time.

### Gaps
- OpenAI's original blog could not be fetched (403). Bucket definitions and annotation-filtering percentages come from secondary sources.
- I found no controlled study of the agentic-vs-single-shot gap as a function of difficulty with the model held fixed.
- I found no SWE-bench study that relates success to "distance from failure to fault" (e.g., stack-trace depth).

## 5. Are mutants valid proxies for real faults in LLM repair evaluation?

### Takeaway
The evidence is mixed and indirect. Classic testing and FL studies show mutants are partial proxies: 73% coupling, but FL results do not transfer and FEP behaviour differs. For LLM repair specifically, I found no controlled study showing LLMs repair seeded mutants more easily than real bugs. One 2025 study of vulnerabilities reports the opposite: LLMs patch real vulnerabilities more effectively than artificial ones. LLM-generated synthetic bugs (BugFarm) were harder for learned APR than mutation-style bugs. Contamination on old real-bug benchmarks such as Defects4J complicates any comparison.

### Cited Findings
- Garg, Khan, Degiovanni & Tang, "Evaluating LLMs for One-Shot Patching of Real and Artificial Vulnerabilities" (arXiv 2511.23408, Nov 2025). LLMs "patch real vulnerabilities more effectively compared to artificial ones". There is large variability across LLMs. [abstract only; magnitudes not extracted] — [arXiv](https://arxiv.org/abs/2511.23408)
- BugFarm (LLM-generated synthetic bugs). A state-of-the-art learned APR tool repaired 28% of BugFarm bugs, against 36% for LEAM mutants and 49% for μBERT mutants. Mutation-style bugs were easier than LLM-crafted subtle bugs. — [BugFarm PDF](https://alirezai.cs.illinois.edu/assets/pdf/bugfarm.pdf)
- NeurIPS 2023, "LLMs of Code Fail at Completing Code with Potential Bugs". Mitigations worked better on synthetic operator-flip bugs (buggy-HumanEval) than on realistic bugs (buggy-FixEval). The authors attribute this to realistic bugs being multiple, mixed with other changes, and more nuanced than single operator changes. — [NeurIPS PDF](https://proceedings.neurips.cc/paper_files/paper/2023/file/819cebb05f993840e8a52d7564c5c282-Paper-Conference.pdf)
- RealiT (2022). Fine-tuning on real bug fixes always significantly beat training on mutants alone. The gain was larger for localization than for repair. — [arXiv 2207.00301](https://arxiv.org/pdf/2207.00301)
- Contamination (2026 preprints).
  - A metamorphic-testing study finds semantics-preserving rewrites lower LLM repair success on Defects4J by about 4–16%, consistent with memorization. — [arXiv 2604.21579](https://arxiv.org/html/2604.21579)
  - Another study finds Defects4J has *low* memorization sensitivity (0.2–0.4) against other benchmarks (0.5–0.8).
  - The two conflict. — [arXiv 2604.13997](https://arxiv.org/html/2604.13997v1)
- SWE-Synth. Humans told synthetic bugs from real ones with only 55% accuracy. [summary only] — [arXiv 2504.14757](https://arxiv.org/pdf/2504.14757)
- Real faults vs mutants on FEP and FL (cross-reference): mutants showed more FEP than real faults [Jahangirova et al.](https://arxiv.org/html/2011.10787), and FL results on artificial faults did not predict real-fault results [Pearson et al.](https://homes.cs.washington.edu/~rjust/publ/fault_localization_effectiveness_icse_2017.pdf).

### Inferences
- For an RTL mutant benchmark, **operator-mutants are likely on the easier end of repair** when localization is given. They are single-token and pattern-regular, and the BugFarm data supports this direction. They may be **harder to detect or localize** than real bugs when they cause masked or propagation-limited failures, per the mutant FEP data. These two effects pull in opposite directions. Report repair-given-localization and end-to-end debugging separately.
- Fresh RTL designs, or mutants of post-cutoff code, reduce the contamination confound seen with Defects4J. Metamorphic rewriting (renaming signals, restructuring always blocks) is a cheap contamination check.
- Recommended validation step: include a small set of real RTL bugs (e.g., from published HDL bug datasets) and check that difficulty covariates rank them similarly to mutants. That checks for the Pearson-style non-transfer.

### Gaps
- I found no direct study comparing LLM repair rates on mutation-operator bugs and on matched real bugs in the same codebase and with the same models.
- The magnitude of the real-vs-artificial vulnerability gap in Garg et al. was not extracted.
- Hardware-specific evidence (Verilog mutant vs real-bug repair) was outside this scope and not searched.
