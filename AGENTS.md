# Lorica

Project code Lr. Independent C++ security component collection, not a server.
Use one responsibility per header/module. No network fetching or third-party
runtime dependency by default. Treat threat-model limits as public contracts.
Never describe bounded views as validating arbitrary pointer lifetime/provenance.
Keep expected bad-input rejection separate from invariant violations.
Do not add custom cryptography, authentication or allocators without design review.
Follow workspace task-worktree/Revisor workflow. Test execution requires the
applicable user authorization; record unexecuted checks explicitly.
