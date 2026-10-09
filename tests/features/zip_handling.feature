Feature: Native .zip Handling in ptbundle
  As a release engineer or cross-domain operator
  I want to pack and unpack plain-text Git bundles directly as single .zip files
  So that I can transfer and audit bundles as single-file packages without manual extraction steps

  Scenario: Pack a delta directly to a .zip archive and unpack into target repo
    Given a source repository with a feature branch
    And a target repository possessing the base commit
    When I pack the delta "main..feature" into a zip archive
    And I unpack the zip archive into the target repository
    Then the target repository should have branch "feature" matching the source

  Scenario: Convert canonical Git bundle to a .zip archive and back
    Given a source repository with a feature branch
    And a canonical Git bundle created from the feature branch
    When I convert the canonical Git bundle into a zip archive
    And I convert the zip archive back into a canonical Git bundle
    Then the synthesized Git bundle passes canonical git bundle verification
    And cloning from the synthesized Git bundle matches the source repository
