Feature: Binary Whitelisting and Quarantine Sidechannel Delivery
  As a security compliance officer
  I want non-whitelisted binary files segregated into a quarantine directory
  So that high-risk assets travel out-of-band on inspected physical media

  Scenario: Non-whitelisted binaries diverted to quarantine during pack
    Given a source repository with a base commit
    And a feature branch containing text files, a whitelisted "png" image, and a non-whitelisted "bin" file
    When I pack the delta with whitelist extension "png"
    Then the bundle should contain the whitelisted image in the blobs directory
    And the non-whitelisted file should be segregated into the quarantine directory with an audit manifest

  Scenario: Unpack fails when required quarantine sidechannel media is omitted
    Given a bundle containing quarantined binary objects
    And a target repository possessing the base commit
    When I attempt to unpack the bundle without specifying a sidechannel directory
    Then the unpack operation should fail with a quarantine error
    And the target repository reference should remain unchanged

  Scenario: Unpack succeeds when sidechannel media is provided
    Given a bundle containing quarantined binary objects
    And a target repository possessing the base commit
    And a mounted sidechannel media directory containing the quarantined objects
    When I unpack the bundle with the sidechannel directory specified
    Then the unpack operation should succeed
    And the target repository should checkout all files including the quarantined binary
