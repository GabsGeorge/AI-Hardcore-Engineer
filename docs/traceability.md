# Rastreabilidade REQ → tarefa → teste

Gerado por `scripts/check_traceability.py` (REQ-INF-04).

| REQ | Tarefa(s) | Teste(s) | Entregue |
|---|---|---|---|
| REQ-API-01 | T030, T075 | tests/contract/test_chat_contract.py, tests/integration/test_chat_flow.py | ✅ |
| REQ-API-02 | T028, T054, T075, T127, T162 | tests/contract/test_admin_api.py, tests/contract/test_chat_contract.py, tests/contract/test_me_conversations.py, tests/contract/test_openapi_fuzz.py, tests/integration/test_admin_invite.py, tests/integration/test_admin_link_merchant.py, tests/integration/test_chat_flow.py | ✅ |
| REQ-API-03 | T015, T020, T028 | tests/contract/test_chat_validation.py | ✅ |
| REQ-API-04 | T016, T031 | tests/integration/test_health.py | ✅ |
| REQ-API-05 | T105, T112 | tests/integration/test_hitl.py, tests/integration/test_me_conversations_isolation.py | ✅ |
| REQ-API-06 | T137, T142 | tests/contract/test_idempotency.py | ✅ |
| REQ-API-07 | T160, T166 | tests/contract/test_stream.py | ✅ |
| REQ-GR-01 | T114, T119, T121 | tests/security/test_injection_direct.py, tests/security/test_injection_identity.py | ✅ |
| REQ-GR-02 | T010, T011, T022, T025, T039, T050, T053, T085 | tests/integration/test_chat_flow.py, tests/integration/test_graph_topology.py, tests/security/test_pii.py, tests/security/test_security_idor.py, tests/unit/test_logging.py, tests/unit/test_pii.py | ✅ |
| REQ-GR-03 | T116, T119 | tests/integration/test_out_of_scope.py | ✅ |
| REQ-GR-04 | T117, T120, T121 | tests/unit/test_output_guardrail.py | ✅ |
| REQ-GR-05 | T082, T115, T121 | tests/integration/test_graph_paths.py, tests/integration/test_knowledge.py, tests/security/test_chat_render.py, tests/security/test_injection_indirect.py | ✅ |
| REQ-HITL-01 | T099, T108 | tests/integration/test_hitl.py | ✅ |
| REQ-HITL-02 | T100, T106, T108, T109 | tests/integration/test_hitl.py | ✅ |
| REQ-HITL-03 | T101, T108, T111 | tests/integration/test_hitl.py | ✅ |
| REQ-HITL-04 | T102, T106, T109 | tests/integration/test_handoff_reply_ui.py, tests/integration/test_side_effect_approval.py | ✅ |
| REQ-HITL-05 | T139, T144 | tests/integration/test_sla.py | ✅ |
| REQ-HITL-06 | T103, T111 | tests/contract/test_handoffs_sort.py, tests/integration/test_hitl.py | ✅ |
| REQ-INF-01 | T034, T035, T154, T164 | tests/unit/test_obs_profile.py | ✅ |
| REQ-INF-02 | T033, T164 | - | ✅ |
| REQ-INF-03 | T035, T164 | - | ✅ |
| REQ-INF-04 | T161, T165, T167, T168 | tests/test_no_stubs.py, tests/unit/test_traceability.py | ✅ |
| REQ-INF-05 | T003, T008, T036, T037 | tests/test_repo_hygiene.py | ✅ |
| REQ-INF-06 | T163, T171, T172, T173 | tests/test_readme.py | ✅ |
| REQ-MEM-01 | T086, T087 | tests/integration/test_chat_flow.py, tests/security/test_conversation_ownership.py, tests/security/test_memory_isolation.py | ✅ |
| REQ-MEM-02 | T123, T125 | tests/integration/test_memory.py | ✅ |
| REQ-MEM-03 | T122, T125 | tests/integration/test_memory.py | ✅ |
| REQ-OBS-01 | T011, T025, T026, T032 | tests/unit/test_logging.py | ✅ |
| REQ-OBS-02 | T145, T150, T154 | tests/integration/test_tracing.py, tests/unit/test_prompt_version.py | ✅ |
| REQ-OBS-03 | T146, T151, T152, T153 | tests/integration/test_metrics.py, tests/unit/test_obs_profile.py | ✅ |
| REQ-OBS-04 | T147, T155 | tests/unit/test_online_eval.py | ✅ |
| REQ-OBS-05 | T148, T156 | tests/contract/test_feedback.py | ✅ |
| REQ-OBS-06 | T157, T158, T168 | tests/integration/test_golden_scenarios.py, tests/unit/test_eval_checks.py | ✅ |
| REQ-ORC-01 | T039, T041, T051, T127, T158 | tests/integration/test_golden_scenarios.py, tests/integration/test_graph_topology.py, tests/unit/test_supervisor_plan.py | ✅ |
| REQ-ORC-02 | T091, T095, T096 | tests/integration/test_graph_parallel.py, tests/integration/test_graph_paths.py | ✅ |
| REQ-ORC-03 | T092, T095 | tests/integration/test_graph_replan.py | ✅ |
| REQ-ORC-04 | T009, T042, T051, T052 | tests/integration/test_graph_budget.py, tests/integration/test_graph_paths.py, tests/unit/test_config.py | ✅ |
| REQ-ORC-05 | T038, T043, T046, T048 | tests/security/test_allowlist.py, tests/unit/test_tool_interfaces.py | ✅ |
| REQ-ORC-06 | T012, T024, T040, T045, T053 | tests/integration/test_graph_state.py, tests/unit/test_migrations.py | ✅ |
| REQ-ORC-07 | T044, T052 | tests/integration/test_language.py | ✅ |
| REQ-RAG-01 | T068, T069, T076, T077, T079 | tests/integration/test_ingest.py, tests/unit/test_crawler.py | ✅ |
| REQ-RAG-02 | T024, T069, T079 | tests/integration/test_ingest.py | ✅ |
| REQ-RAG-03 | T070, T078 | tests/unit/test_chunking.py | ✅ |
| REQ-RAG-04 | T071, T080, T159 | tests/integration/test_retriever.py, tests/integration/test_retriever_resilience.py, tests/unit/test_bm25.py, tests/unit/test_retrieval_metrics.py, tests/unit/test_rrf.py | ✅ |
| REQ-RAG-05 | T072, T080 | tests/integration/test_multi_query.py | ✅ |
| REQ-RAG-06 | T073, T082, T083 | tests/integration/test_knowledge.py | ✅ |
| REQ-RAG-07 | T073, T080, T083 | tests/integration/test_knowledge.py | ✅ |
| REQ-RAG-08 | T074, T081 | tests/unit/test_web_search.py | ✅ |
| REQ-REL-01 | T097, T134, T140 | tests/integration/test_retriever_resilience.py, tests/integration/test_support_resilience.py, tests/unit/test_resilience.py | ✅ |
| REQ-REL-02 | T135, T141 | tests/unit/test_fallback.py | ✅ |
| REQ-REL-03 | T134, T140 | tests/unit/test_resilience.py | ✅ |
| REQ-REL-04 | T169, T170 | - | ✅ |
| REQ-SEC-01 | T009, T013, T019, T027 | tests/security/test_admin_rbac.py, tests/security/test_api_auth.py, tests/unit/test_auth.py, tests/unit/test_config.py | ✅ |
| REQ-SEC-02 | T014, T029, T030, T087 | tests/integration/test_chat_flow.py, tests/integration/test_me_conversations_isolation.py, tests/security/test_conversation_ownership.py, tests/security/test_security_idor.py | ✅ |
| REQ-SEC-03 | T038, T045, T046, T060, T063, T064, T084 | tests/security/test_injection_identity.py, tests/security/test_tools_identity.py, tests/unit/test_tool_interfaces.py | ✅ |
| REQ-SEC-04 | T003, T004, T006, T008, T019, T036, T037, T168 | tests/integration/test_metrics.py, tests/test_repo_hygiene.py | ✅ |
| REQ-SEC-05 | T002, T033, T168 | - | ✅ |
| REQ-SEC-06 | T104, T110 | tests/contract/test_me_conversations.py, tests/integration/test_hitl.py, tests/security/test_handoff_rbac.py | ✅ |
| REQ-SEC-07 | T029, T064, T128, T129 | tests/contract/test_stream.py, tests/security/test_admin_audit_no_pii.py, tests/security/test_audit.py, tests/security/test_security_idor.py | ✅ |
| REQ-SEC-08 | T136, T142 | tests/security/test_audit.py, tests/security/test_rate_limit.py | ✅ |
| REQ-SEC-09 | T138, T143, T144 | tests/integration/test_lgpd.py, tests/integration/test_me_delete_account.py, tests/integration/test_sla.py | ✅ |
| REQ-SUP-01 | T059, T061, T063, T064, T066 | tests/integration/test_support_agent.py, tests/unit/test_support_tools.py | ✅ |
| REQ-SUP-02 | T058, T062 | tests/unit/test_seed.py | ✅ |
| REQ-SUP-03 | T093, T097 | tests/integration/test_support_resilience.py | ✅ |
| REQ-SUP-04 | T094, T098 | tests/integration/test_support_kb.py | ✅ |
