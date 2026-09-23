Feature: Delta Transfer Between Repositories
  As a developer in a secure cross-domain environment
  I want to transfer Git revision deltas as plain-text bundles
  So that repositories can be synchronized without binary packfiles or network access

  Scenario: Export and import a branch delta between repositories
    Given a source repository with a base commit on branch "main"
    And a feature branch "feature" with text commits ahead of "main"
    And a target repository cloned from "main"
    When I pack the delta "main..feature" into a bundle
    And I unpack the bundle into the target repository
    Then the target repository should have branch "feature" matching the source
    And git fsck in the target repository should report no corruption

  Scenario: Export and import a full repository without prerequisites
    Given a source repository with an initial commit on branch "main"
    And an empty destination repository
    When I pack the full branch "main" into a bundle
    And I unpack the bundle into the destination repository
    Then the destination repository should have branch "main" matching the source
    And git fsck in the destination repository should report no corruption
