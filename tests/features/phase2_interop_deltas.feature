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

  Scenario: Single-commit PR incremental pack with thin deltas against base commit
    Given a source repository with a wide multi-file tree on "main"
    And a single-commit feature branch modifying text files and directory trees
    When I pack the revision delta as a thin bundle
    Then the generated bundle contains thin deltas referencing basis objects from "main"
    And the basis objects from "main" are not bundled in the package
    And unpacking the thin bundle into a clone of "main" reproduces the exact feature state

  Scenario: Single-commit PR pack with no-thin enforces complete self-containment
    Given a source repository with a wide multi-file tree on "main"
    And a single-commit feature branch modifying text files and directory trees
    When I pack the revision delta with no-thin specified
    Then the generated bundle contains zero delta files
    And all objects are stored in full for standalone self-containment

