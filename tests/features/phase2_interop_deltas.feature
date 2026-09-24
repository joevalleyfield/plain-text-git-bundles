Feature: Plain-Text Delta Compression and Git Bundle Interoperability
  As a secure software engineer or ingress auditor
  I want iterative text and tree modifications compressed as plain-text unified diffs
  And I want bidirectional conversion between canonical Git .bundle files and ptbundle trees
  So that bundle sizes remain minimal, audits remain transparent, and canonical Git tools interoperate seamlessly

  Scenario: Multi-commit text and tree plain-text delta compression
    Given a source repository with an initial commit containing a multi-file tree
    And multiple successive commits iteratively modifying text files
    When I pack the revision delta with plain-text delta compression enabled
    Then the generated bundle should contain delta tree and blob files
    And unpacking the bundle into a target repository reproduces the exact Git commits and tree state

  Scenario: Bidirectional conversion between Git bundle and ptbundle
    Given a source repository with a feature branch
    And a canonical Git bundle created from the feature branch
    When I convert the canonical Git bundle into a ptbundle directory
    And I convert the ptbundle directory back into a canonical Git bundle
    Then the synthesized Git bundle passes canonical git bundle verification
    And cloning from the synthesized Git bundle matches the source repository
