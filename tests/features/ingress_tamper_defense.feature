Feature: Ingress Defense and Tamper Rejection
  As an ingress guard operator
  I want corrupted, altered, or malicious bundles rejected before repository modification
  So that bad data cannot corrupt the Git object store or overwrite arbitrary refs

  Scenario: Tampered object payload in transit is rejected
    Given a valid bundle created from a feature branch
    And a target repository possessing the base commit
    When an attacker alters the content of a blob file in the bundle
    And I attempt to unpack the altered bundle into the target repository
    Then the unpack operation should fail with a cryptographic mismatch error
    And the target repository reference should remain unchanged

  Scenario: Missing prerequisite commit halts unpack without modifying repository
    Given a valid bundle requiring a specific base commit
    And an empty target repository lacking the prerequisite commit
    When I attempt to unpack the bundle into the target repository
    Then the unpack operation should fail with a missing prerequisite error
    And the target repository should contain no references
